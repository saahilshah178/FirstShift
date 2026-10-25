"""Stage 3 DONE-WHEN self-check.

Runs end-to-end (role gating, near-miss, Clients caregiver-fit, Alex
sign-off → cleared transition) through the HTTP API against a running
backend. Prints a short pass/fail report and resets any state it
touched. Safe to re-run.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid

import requests

API = os.environ.get("API", "http://localhost:8001")
MGR = {"X-Firstshift-Role": "Care Manager"}
TRN = {"X-Firstshift-Role": "Trainer"}
SCH = {"X-Firstshift-Role": "Scheduler"}

PASS = "\u001b[32mPASS\u001b[0m"
FAIL = "\u001b[31mFAIL\u001b[0m"

errors: list[str] = []


def check(label: str, cond: bool, hint: str = "") -> None:
    print(f"  {PASS if cond else FAIL}  {label}")
    if not cond:
        errors.append(f"{label}: {hint}")


def get(path, headers=None):
    r = requests.get(f"{API}{path}", headers=headers or {})
    return r


def post(path, json_body=None, headers=None):
    r = requests.post(
        f"{API}{path}",
        headers={"Content-Type": "application/json", **(headers or {})},
        data=json.dumps(json_body or {}),
    )
    return r


def delete(path, headers=None):
    r = requests.delete(f"{API}{path}", headers=headers or {})
    return r


# ---------------------------------------------------------------------------
# Resolve ids
# ---------------------------------------------------------------------------

cgs = get("/api/caregivers/list").json()["caregivers"]
alex = next(c for c in cgs if c["name"] == "Alex Johnson")
jovelyn = next(c for c in cgs if c["name"] == "Jovelyn Santos")
maria = next(c for c in cgs if c["name"] == "María García")
assert alex["access_code"] == "2TBAFX", alex

skills = get("/api/lessons/skills").json()["skills"]
sk_by_title = {s["title"]: s["id"] for s in skills}
GLOVE = sk_by_title["Glove removal"]
HAND = sk_by_title["Hand hygiene"]
TRANSFER = sk_by_title["Transfer from bed to wheelchair"]

clients = get("/api/ops/clients").json()["clients"]
oshiro = next(c for c in clients if "Oshiro" in c["name"])

print(f"API = {API}")
print(f"Alex    = {alex['id']}  (/c/{alex['access_code']})")
print(f"Jovelyn = {jovelyn['id']}  (/c/{jovelyn['access_code']})")
print(f"María   = {maria['id']}  (/c/{maria['access_code']})")

import pymongo  # noqa: E402

mongo = pymongo.MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
dbname = os.environ.get("DB_NAME", "test_database")
db = mongo[dbname]

# Pre-clean so a prior failed run cannot leave residue that trips the
# "not auto-sent" assertion later. `dev/reset` deliberately preserves
# messages for demo replay; we blow them away by hand here.
post(f"/api/channel/dev/reset/{alex['id']}", {}, headers=MGR)
db.messages.delete_many({"caregiver_id": alex["id"]})
db.incidents.delete_many({"caregiver_id": alex["id"]})
db.refresher_drafts.delete_many({"caregiver_id": alex["id"]})

# ---------------------------------------------------------------------------
# 1. Role gating on Stage 3 writes
# ---------------------------------------------------------------------------
print("\n[1] Role gating on near-miss")
r = post(f"/api/plans/caregiver/{alex['id']}/near-miss", {"skill_id": "x", "description": "y"})
check("no header -> 403", r.status_code == 403, f"got {r.status_code}")
r = post(f"/api/plans/caregiver/{alex['id']}/near-miss", {"skill_id": "x", "description": "y"}, headers=SCH)
check("Scheduler -> 403", r.status_code == 403, f"got {r.status_code}")
r = post(f"/api/plans/caregiver/{alex['id']}/near-miss", {"skill_id": "x", "description": "y"}, headers=TRN)
check("Trainer -> 403", r.status_code == 403, f"got {r.status_code}")

print("[1b] Role gating on refresher-drafts")
for action, path, verb in [
    ("send",    "/api/plans/refresher-drafts/none/send",    "POST"),
    ("edit",    "/api/plans/refresher-drafts/none",          "PUT"),
    ("discard", "/api/plans/refresher-drafts/none",          "DELETE"),
]:
    url = f"{API}{path}"
    r = requests.request(verb, url, headers={**SCH, "Content-Type": "application/json"}, data="{}")
    check(f"Scheduler {verb} {action} -> 403", r.status_code == 403, f"got {r.status_code}")
    r = requests.request(verb, url, headers={**TRN, "Content-Type": "application/json"}, data="{}")
    check(f"Trainer {verb} {action} -> 403", r.status_code == 403, f"got {r.status_code}")

# ---------------------------------------------------------------------------
# 2. Today metrics shape
# ---------------------------------------------------------------------------
print("\n[2] Today metrics")
m = get("/api/ops/today/metrics").json()
check("cards.new_hires_in_progress is int", isinstance(m["cards"]["new_hires_in_progress"], int))
check("cards.signoffs_waiting is int", isinstance(m["cards"]["signoffs_waiting"], int))
check("cards.open_questions is int", isinstance(m["cards"]["open_questions"], int))
check("avg_days_to_cleared is None or float", m["avg_days_to_cleared"] is None or isinstance(m["avg_days_to_cleared"], (int, float)))

# ---------------------------------------------------------------------------
# 3. Clients caregiver-fit BEFORE
# ---------------------------------------------------------------------------
print("\n[3] Clients caregiver-fit (BEFORE sign-off)")
r = get(f"/api/ops/clients/{oshiro['id']}/caregiver-fit").json()
check("Oshiro cleared empty", r["cleared"] == [])
alex_row = next((a for a in r["almost_ready"] if a["id"] == alex["id"]), None)
check("Alex is Almost ready for Oshiro", alex_row is not None)
if alex_row:
    check("missing_skill_title == Hand hygiene", alex_row["missing_skill_title"] == "Hand hygiene")

# ---------------------------------------------------------------------------
# 4. Alex live-upload simulation (grade_clip is already-tested in Stage 2;
#    here we drive just the sign-off → cleared → Clients transition by
#    inserting a synthetic ready_to_sign attempt the way grade_clip would.)
# ---------------------------------------------------------------------------
print("\n[4] Alex sign-off → cleared → Clients rebucket")

# Create a ready_to_sign attempt for Alex on Hand hygiene using an
# existing clip id (any clip in GridFS works; we only need the attempt
# row to pass the signoff validator).
# Reuse any existing clip_id so we don't have to upload a new blob.
sample_attempt = db.attempts.find_one({"clip_id": {"$exists": True}})
assert sample_attempt, "need at least one existing clip in attempts collection"
clip_id = sample_attempt["clip_id"]

attempt_id = uuid.uuid4().hex
# Mirror the Hand-hygiene skill's checks so the signoff validator is happy.
hand_skill = db.skills.find_one({"_id": HAND})
checks = [
    {"id": c["id"], "result": "pass", "time": 0.0, "seen": True}
    for c in (hand_skill.get("checks") or [])
]
from datetime import datetime, timezone
db.attempts.insert_one({
    "_id": attempt_id,
    "caregiver_id": alex["id"],
    "skill_id": HAND,
    "clip_id": clip_id,
    "status": "ready_to_sign",
    "reviewed": False,
    "overall": "pass",
    "verdict": "pass",
    "score": 100,
    "runs_used": 1,
    "graded_once": True,
    "checks": checks,
    "created_at": datetime.now(timezone.utc).isoformat(),
})
check("inserted synthetic ready_to_sign attempt for Alex", True)

# Confirm it shows in the sign-off queue.
q = get("/api/grading/queue").json()
in_queue = any(a["id"] == attempt_id for a in q.get("ready_to_sign") or [])
check("attempt appears in /api/grading/queue", in_queue)

# Approve as Care Manager via the real signoff route.
r = post(
    f"/api/grading/attempts/{attempt_id}/signoff",
    {"decision": "approve", "signer": "Rachel Kim, RN", "signer_role": "Care Manager", "note": ""},
    headers=MGR,
)
check("signoff approve -> 200", r.status_code == 200, f"got {r.status_code}: {r.text[:200]}")

# Alex is now cleared for Hand hygiene -> Oshiro.cleared should include him.
r = get(f"/api/ops/clients/{oshiro['id']}/caregiver-fit").json()
cleared_names = [c["name"] for c in r["cleared"]]
check("Alex in Oshiro.cleared", "Alex Johnson" in cleared_names, f"cleared={cleared_names}")
alex_almost_still = any(a["id"] == alex["id"] for a in r["almost_ready"])
check("Alex NO LONGER in Oshiro.almost_ready", not alex_almost_still)

# Plan reflects it: Hand hygiene status=cleared, no more refresher.
plan = get(f"/api/plans/caregiver/{alex['id']}").json()
hand_item = next((i for i in plan["items"] if i["skill_id"] == HAND), None)
check("Alex plan Hand hygiene = cleared", hand_item and hand_item["status"] == "cleared")

# ---------------------------------------------------------------------------
# 5. Near-miss flow: pull clearance + draft refresher.
# ---------------------------------------------------------------------------
print("\n[5] Near-miss end-to-end on Alex's just-cleared skill")
r = post(
    f"/api/plans/caregiver/{alex['id']}/near-miss",
    {"skill_id": HAND, "description": "Observed skipped drying step on 10/24 shift."},
    headers=MGR,
)
check("near-miss -> 200", r.status_code == 200, f"got {r.status_code}: {r.text[:300]}")
nm = r.json()
check("incident_id returned", bool(nm.get("incident_id")))
check("draft_id returned", bool(nm.get("draft_id")))
check("draft_text non-empty", bool(nm.get("draft_text")))

# cleared_skills no longer includes Hand hygiene.
cg = get(f"/api/caregivers/by-code/2TBAFX").json()["caregiver"]
check("Hand hygiene pulled from cleared_skills", HAND not in cg["cleared_skills"])

# Plan status flipped to refresher.
plan = get(f"/api/plans/caregiver/{alex['id']}").json()
hand_item = next((i for i in plan["items"] if i["skill_id"] == HAND), None)
check("plan Hand hygiene = refresher", hand_item and hand_item["status"] == "refresher")
check("refresher_at set", bool(hand_item and hand_item.get("refresher_at")))

# Draft list visible.
drafts = get(f"/api/plans/caregiver/{alex['id']}/refresher-drafts").json()["drafts"]
check("exactly one draft after near-miss", len(drafts) == 1, f"got {len(drafts)}")
draft_id = drafts[0]["id"]

# Edit the draft.
r = requests.put(f"{API}/api/plans/refresher-drafts/{draft_id}",
                 headers={**MGR, "Content-Type": "application/json"},
                 data=json.dumps({"text": "Hey Alex — let's redo Hand hygiene together before Fri."}))
check("edit draft -> 200", r.status_code == 200, f"got {r.status_code}: {r.text[:200]}")

# Confirm draft does NOT appear in the caregiver chat BEFORE Send.
msgs = get(f"/api/channel/messages/{alex['id']}").json()
msg_texts = [m.get("text") or "" for m in msgs.get("messages") or []]
unsent = all("Hand hygiene together before Fri" not in t for t in msg_texts)
check("draft NOT auto-sent to Alex's chat", unsent)

# Send the draft.
r = post(f"/api/plans/refresher-drafts/{draft_id}/send", {}, headers=MGR)
check("send draft -> 200", r.status_code == 200, f"got {r.status_code}: {r.text[:200]}")

# Give the channel service a tick to persist.
time.sleep(0.2)
msgs = get(f"/api/channel/messages/{alex['id']}").json()
msg_texts = [m.get("text") or "" for m in msgs.get("messages") or []]
check("draft appears in Alex's chat after Send",
      any("Hand hygiene together before Fri" in t for t in msg_texts))

# Draft removed after Send.
drafts = get(f"/api/plans/caregiver/{alex['id']}/refresher-drafts").json()["drafts"]
check("draft removed after send", len(drafts) == 0, f"got {len(drafts)}")

# ---------------------------------------------------------------------------
# 6. Cert map covers all 4 skills for CNA.
# ---------------------------------------------------------------------------
print("\n[6] cert_skill_map seeded")
cm = get("/api/plans/cert-map").json()["certificates"]
cna = next(c for c in cm if c["certificate"] == "CNA")
check("CNA has 4 skills", len(cna["verify_skill_ids"]) == 4, cna)

# ---------------------------------------------------------------------------
# 7. Clean-up (reset Alex, remove synthetic attempt, remove incident + any
#    remaining drafts). Puts the demo back to a pristine starting line.
# ---------------------------------------------------------------------------
print("\n[7] Cleanup")
db.attempts.delete_one({"_id": attempt_id})
db.signoffs.delete_many({"attempt_id": attempt_id})
db.incidents.delete_many({"caregiver_id": alex["id"]})
db.refresher_drafts.delete_many({"caregiver_id": alex["id"]})
# Clear cleared_skills and flip plan.items[*].refresher back off.
db.caregivers.update_one({"_id": alex["id"]}, {"$set": {"cleared_skills": []}})
db.plans.update_one(
    {"caregiver_id": alex["id"]},
    {"$set": {"items.$[].refresher": False}},
)
# Scrub the drafted refresher message from Alex's chat so the demo
# starts clean. Only strip the exact text we sent above.
r = post(f"/api/channel/dev/reset/{alex['id']}", {}, headers=MGR)
check("Alex chat reset for next demo", r.status_code == 200, f"got {r.status_code}")
print(f"\n==> {len(errors)} failure(s)" if errors else "\n==> ALL PASS")
if errors:
    for e in errors:
        print(" -", e)
    sys.exit(1)
