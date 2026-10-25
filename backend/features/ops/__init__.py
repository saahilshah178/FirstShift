"""ops feature — agency ops endpoints.

Routes mounted at `/api/ops`:

Phase-1 (unchanged):
- GET `/`           -> placeholder marker.
- GET `/caregivers` -> list caregivers (name, language, hired_at, agency_id).
                       Optional `?sort=hired_at_desc` for the "New hires" view.
- GET `/clients`    -> list clients with `required_skills` resolved to titles.

Stage 3:
- GET `/today/metrics`      -> 3 card counts + headline avg-time-to-cleared.
- GET `/today/cleared-days` -> per-caregiver drilldown behind the headline.
- GET `/clients/{id}/caregiver-fit` -> cleared + almost-ready caregivers
                                       for one client.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query

from db import get_db

router = APIRouter()


@router.get("/")
async def placeholder() -> dict:
    return {"feature": "ops", "status": "placeholder"}


def _projection_caregiver() -> dict:
    return {
        "_id": 0,
        "id": "$_id",
        "agency_id": 1,
        "name": 1,
        "language": 1,
        "hired_at": 1,
        "experience_note": 1,
        "cleared_skills": 1,
        "access_code": 1,
    }


@router.get("/caregivers")
async def list_caregivers(sort: str | None = Query(default=None)):
    db = get_db()
    cursor = db.caregivers.aggregate([
        {"$project": _projection_caregiver()},
    ])
    rows = await cursor.to_list(length=1000)
    if sort == "hired_at_desc":
        rows.sort(key=lambda r: r.get("hired_at", ""), reverse=True)
    else:
        rows.sort(key=lambda r: r.get("name", ""))
    return {"caregivers": rows}


@router.get("/clients")
async def list_clients():
    db = get_db()
    clients = await db.clients.find({}, {"_id": 1, "agency_id": 1, "name": 1, "required_skills": 1}).to_list(length=1000)
    skills = await db.skills.find({}, {"_id": 1, "title": 1}).to_list(length=1000)
    title_by_id = {s["_id"]: s["title"] for s in skills}
    result = []
    for c in clients:
        result.append({
            "id": c["_id"],
            "agency_id": c.get("agency_id"),
            "name": c.get("name"),
            "required_skills": [
                {"id": sid, "title": title_by_id.get(sid, "unknown")}
                for sid in c.get("required_skills", [])
            ],
        })
    result.sort(key=lambda r: r["name"])
    return {"clients": result}


# ---------------------------------------------------------------------------
# Stage 3 — Today metrics
# ---------------------------------------------------------------------------

def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


# Mongo aggregation pipeline for the Today "avg days to cleared" headline.
#
# The brief pins this to **server-side $match + $group + $avg** (no
# Python averaging). We join signoffs → caregivers → plans with
# `$lookup`, filter down to caregivers who have an approved sign-off on
# every required skill AND the matching entry in `cleared_skills`, then
# $group on `_id: null` with `$avg` to produce the headline, plus a
# `$push` of per-caregiver rows for the drilldown.
def _avg_days_pipeline() -> list[dict]:
    return [
        # 1. Only count approved sign-offs.
        {"$match": {"decision": "approve"}},
        # 2. Group approved sign-offs by caregiver — we want the max `at`
        # (the moment they crossed the "all items cleared" line) and the
        # set of skills they've been approved on.
        {"$group": {
            "_id": "$caregiver_id",
            "approved_skills": {"$addToSet": "$skill_id"},
            "fully_cleared_at": {"$max": "$at"},
        }},
        # 3. Join caregiver (needs `hired_at`, `name`, `cleared_skills`).
        {"$lookup": {
            "from": "caregivers",
            "localField": "_id",
            "foreignField": "_id",
            "as": "cg",
        }},
        {"$unwind": "$cg"},
        # 4. Join plan (needs the plan's `items.skill_id` list to decide
        # "fully cleared").
        {"$lookup": {
            "from": "plans",
            "localField": "_id",
            "foreignField": "caregiver_id",
            "as": "plan",
        }},
        {"$unwind": "$plan"},
        {"$set": {
            "required_ids": "$plan.items.skill_id",
            "cleared_skills": {"$ifNull": ["$cg.cleared_skills", []]},
        }},
        # 5. Keep only caregivers whose plan is non-empty AND every
        # required skill is both approved AND in cleared_skills.
        {"$set": {
            "missing_from_cleared": {"$setDifference": ["$required_ids", "$cleared_skills"]},
            "missing_from_approved": {"$setDifference": ["$required_ids", "$approved_skills"]},
        }},
        {"$match": {
            "required_ids": {"$ne": []},
            "missing_from_cleared": {"$size": 0},
            "missing_from_approved": {"$size": 0},
        }},
        # 6. Days-to-cleared, computed in Mongo.
        {"$set": {
            "days": {"$divide": [
                {"$subtract": [
                    {"$dateFromString": {"dateString": "$fully_cleared_at"}},
                    {"$dateFromString": {"dateString": "$cg.hired_at"}},
                ]},
                86_400_000,
            ]},
        }},
        # 7. Facet: one $group for the headline avg, one projection for
        # the drilldown rows. The brief wants $match + $group + $avg; the
        # facet keeps both results in a single server round-trip.
        {"$facet": {
            "headline": [
                {"$group": {
                    "_id": None,
                    "avg": {"$avg": "$days"},
                    "count": {"$sum": 1},
                }},
            ],
            "rows": [
                {"$project": {
                    "_id": 0,
                    "caregiver_id": "$_id",
                    "name": "$cg.name",
                    "hired_at": "$cg.hired_at",
                    "fully_cleared_at": "$fully_cleared_at",
                    "days": {"$round": ["$days", 1]},
                }},
                {"$sort": {"days": 1}},
            ],
        }},
    ]


async def _fully_cleared_summary(db) -> dict:
    """Run the aggregation and return `{avg_days, count, rows}`.

    Falls back to `{avg_days: None, count: 0, rows: []}` when no
    caregiver is fully cleared yet (empty-state copy "Not enough data
    yet" in the UI).
    """
    cursor = db.signoffs.aggregate(_avg_days_pipeline())
    result = await cursor.to_list(length=1)
    if not result:
        return {"avg_days": None, "count": 0, "rows": []}
    doc = result[0]
    headline = (doc.get("headline") or [{}])[0]
    avg = headline.get("avg")
    count = headline.get("count") or 0
    rows = doc.get("rows") or []
    return {
        "avg_days": None if avg is None else round(float(avg), 1),
        "count": int(count),
        "rows": rows,
    }


@router.get("/today/metrics")
async def today_metrics() -> dict:
    """Three cards + headline metric for the Today page (Stage 3 — E + F).

    - new_hires_in_progress: hired in last 30 days, plan NOT fully cleared.
    - signoffs_waiting:      attempts with status=ready_to_sign AND NOT reviewed.
    - open_questions:        inbox questions without an answer timestamp.
    - avg_days_to_cleared:   null when no caregiver is fully cleared yet.
    """
    db = get_db()

    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    caregivers = await db.caregivers.find({}, {"_id": 1, "hired_at": 1, "cleared_skills": 1}).to_list(length=2000)
    plans = await db.plans.find({}, {"caregiver_id": 1, "items": 1}).to_list(length=2000)
    plan_by_caregiver = {p["caregiver_id"]: p for p in plans}

    new_hires_in_progress = 0
    for c in caregivers:
        if (c.get("hired_at") or "") < thirty_days_ago:
            continue
        plan = plan_by_caregiver.get(c["_id"])
        if not plan:
            continue
        items = plan.get("items") or []
        required_ids = {i["skill_id"] for i in items}
        cleared = set(c.get("cleared_skills") or [])
        if required_ids and not required_ids.issubset(cleared):
            new_hires_in_progress += 1

    signoffs_waiting = await db.attempts.count_documents(
        {"status": "ready_to_sign", "reviewed": {"$ne": True}},
    )

    open_questions = await db.questions.count_documents(
        {"$or": [{"answered_at": None}, {"answered_at": {"$exists": False}}]},
    )

    summary = await _fully_cleared_summary(db)
    return {
        "cards": {
            "new_hires_in_progress": new_hires_in_progress,
            "signoffs_waiting": signoffs_waiting,
            "open_questions": open_questions,
        },
        "avg_days_to_cleared": summary["avg_days"],
        "fully_cleared_count": summary["count"],
    }


@router.get("/today/cleared-days")
async def today_cleared_days() -> dict:
    """Per-caregiver drilldown behind the headline metric. Sorted asc by days."""
    db = get_db()
    summary = await _fully_cleared_summary(db)
    return {"rows": summary["rows"]}


# ---------------------------------------------------------------------------
# Stage 3 — Clients caregiver-fit
# ---------------------------------------------------------------------------

@router.get("/clients/{client_id}/caregiver-fit")
async def clients_caregiver_fit(client_id: str) -> dict:
    """Cleared + almost-ready caregivers for a client.

    - "Cleared for this client" — caregivers in the same agency whose
      `cleared_skills` contain ALL `required_skills` of the client
      (MongoDB `$all`).
    - "Almost ready" — caregivers in the same agency missing EXACTLY ONE
      required skill; the missing skill is named per row.
    """
    db = get_db()
    client = await db.clients.find_one({"_id": client_id})
    if not client:
        raise HTTPException(status_code=404, detail="client not found")
    required = list(client.get("required_skills") or [])
    agency_id = client.get("agency_id")
    skills = await db.skills.find(
        {"_id": {"$in": required}},
        {"_id": 1, "title": 1},
    ).to_list(length=200)
    title_by_id = {s["_id"]: s["title"] for s in skills}

    if not required:
        return {
            "client": {"id": client["_id"], "name": client.get("name"), "required_skills": []},
            "cleared": [],
            "almost_ready": [],
        }

    agency_filter = {"agency_id": agency_id} if agency_id else {}

    # Cleared — $all means every required id appears in cleared_skills.
    cleared_rows = await db.caregivers.find(
        {**agency_filter, "cleared_skills": {"$all": required}},
        {"_id": 1, "name": 1, "access_code": 1, "language": 1, "hired_at": 1},
    ).to_list(length=500)
    cleared_rows.sort(key=lambda r: r.get("name") or "")

    # Almost ready — missing exactly one required skill.
    agency_cgs = await db.caregivers.find(
        agency_filter,
        {"_id": 1, "name": 1, "access_code": 1, "language": 1, "hired_at": 1, "cleared_skills": 1},
    ).to_list(length=2000)
    required_set = set(required)
    almost: list[dict] = []
    for c in agency_cgs:
        cleared = set(c.get("cleared_skills") or [])
        missing = list(required_set - cleared)
        if len(missing) == 1:
            missing_id = missing[0]
            almost.append({
                "id": c["_id"],
                "name": c.get("name"),
                "access_code": c.get("access_code"),
                "language": c.get("language"),
                "hired_at": c.get("hired_at"),
                "missing_skill_id": missing_id,
                "missing_skill_title": title_by_id.get(missing_id, "unknown"),
            })
    almost.sort(key=lambda r: r.get("name") or "")

    return {
        "client": {
            "id": client["_id"],
            "name": client.get("name"),
            "required_skills": [
                {"id": sid, "title": title_by_id.get(sid, "unknown")}
                for sid in required
            ],
        },
        "cleared": [
            {
                "id": r["_id"],
                "name": r.get("name"),
                "access_code": r.get("access_code"),
                "language": r.get("language"),
                "hired_at": r.get("hired_at"),
            }
            for r in cleared_rows
        ],
        "almost_ready": almost,
    }
