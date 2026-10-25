"""Stage 4 fixup verification: POST /api/channel/dev/reset/{caregiver_id}
must also clear plans.items[].refresher and delete refresher_drafts, while
preserving incidents (audit).
"""
import os
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "https://firstshift-preview.preview.emergentagent.com"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

ALEX_ID = "44c9449a6ebd423486229f0bec62dbb8"
MGR = {"X-Firstshift-Role": "Care Manager"}
SCHED = {"X-Firstshift-Role": "Scheduler"}
TRAINER = {"X-Firstshift-Role": "Trainer"}


@pytest.fixture(scope="module")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module")
def glove_skill_id():
    r = requests.get(f"{BASE_URL}/api/lessons/skills", timeout=15)
    assert r.status_code == 200, r.text
    skills = r.json().get("skills") or r.json()
    if isinstance(skills, dict):
        skills = skills.get("skills", [])
    for s in skills:
        if (s.get("title") or "").strip().lower() == "glove removal":
            return s.get("id") or s.get("_id") or s.get("skill_id")
    pytest.fail(f"Glove removal skill not found in {skills}")


def _prime_cleared_skill(mongo, skill_id):
    """Ensure Glove removal is in Alex's cleared_skills so near-miss works."""
    mongo.caregivers.update_one(
        {"_id": ALEX_ID},
        {"$addToSet": {"cleared_skills": skill_id}},
    )


def test_role_gating_missing_header():
    r = requests.post(f"{BASE_URL}/api/channel/dev/reset/{ALEX_ID}", timeout=15)
    assert r.status_code == 403, r.text
    body = r.json()
    assert body.get("detail", {}).get("reason") == "role_required" or body.get("reason") == "role_required", body


def test_role_gating_scheduler():
    r = requests.post(f"{BASE_URL}/api/channel/dev/reset/{ALEX_ID}", headers=SCHED, timeout=15)
    assert r.status_code == 403, r.text
    body = r.json()
    reason = body.get("detail", {}).get("reason") if isinstance(body.get("detail"), dict) else body.get("reason")
    assert reason == "role_not_allowed", body


def test_role_gating_trainer():
    r = requests.post(f"{BASE_URL}/api/channel/dev/reset/{ALEX_ID}", headers=TRAINER, timeout=15)
    assert r.status_code == 403, r.text
    body = r.json()
    reason = body.get("detail", {}).get("reason") if isinstance(body.get("detail"), dict) else body.get("reason")
    assert reason == "role_not_allowed", body


def test_care_manager_reset_succeeds_baseline():
    r = requests.post(f"{BASE_URL}/api/channel/dev/reset/{ALEX_ID}", headers=MGR, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert "refresher_cleared" in body
    assert "drafts_deleted" in body


def test_near_miss_then_reset_clears_refresher(mongo, glove_skill_id):
    # Prime: ensure Alex has Glove removal cleared
    _prime_cleared_skill(mongo, glove_skill_id)

    # Step 1: trigger near-miss
    nm = requests.post(
        f"{BASE_URL}/api/plans/caregiver/{ALEX_ID}/near-miss",
        headers=MGR,
        json={"skill_id": glove_skill_id, "description": "test near-miss during Stage 4 fixup verification"},
        timeout=15,
    )
    assert nm.status_code in (200, 201), f"near-miss failed: {nm.status_code} {nm.text}"

    # Step 2: verify precondition
    plan_r = requests.get(f"{BASE_URL}/api/plans/caregiver/{ALEX_ID}", timeout=15)
    assert plan_r.status_code == 200, plan_r.text
    plan = plan_r.json()
    items = plan.get("items") or plan.get("plan", {}).get("items") or []
    glove_item = next((it for it in items if it.get("skill_id") == glove_skill_id), None)
    assert glove_item is not None, f"Glove item not in plan: {items}"
    assert glove_item.get("status") == "refresher", f"status should be refresher, got {glove_item}"

    drafts_r = requests.get(f"{BASE_URL}/api/plans/caregiver/{ALEX_ID}/refresher-drafts", timeout=15)
    assert drafts_r.status_code == 200, drafts_r.text
    pre_drafts = drafts_r.json().get("drafts", [])
    assert len(pre_drafts) >= 1, f"expected drafts, got {pre_drafts}"

    # Capture incidents count pre-reset
    inc_pre = requests.get(f"{BASE_URL}/api/plans/caregiver/{ALEX_ID}/incidents", timeout=15)
    assert inc_pre.status_code == 200, inc_pre.text
    pre_incidents = inc_pre.json().get("incidents", [])
    assert len(pre_incidents) >= 1, f"expected incidents, got {pre_incidents}"

    # Step 3: reset
    reset_r = requests.post(f"{BASE_URL}/api/channel/dev/reset/{ALEX_ID}", headers=MGR, timeout=15)
    assert reset_r.status_code == 200, reset_r.text
    reset_body = reset_r.json()
    assert reset_body.get("refresher_cleared", 0) > 0, f"refresher_cleared should be >0: {reset_body}"
    assert reset_body.get("drafts_deleted", 0) > 0, f"drafts_deleted should be >0: {reset_body}"

    # Step 4a: Glove item no longer refresher
    plan2 = requests.get(f"{BASE_URL}/api/plans/caregiver/{ALEX_ID}", timeout=15).json()
    items2 = plan2.get("items") or plan2.get("plan", {}).get("items") or []
    glove2 = next((it for it in items2 if it.get("skill_id") == glove_skill_id), None)
    assert glove2 is not None
    assert glove2.get("status") != "refresher", f"status should not be refresher: {glove2}"

    # Step 4b: zero drafts
    drafts2 = requests.get(f"{BASE_URL}/api/plans/caregiver/{ALEX_ID}/refresher-drafts", timeout=15).json()
    assert drafts2.get("drafts", []) == [], f"drafts should be empty: {drafts2}"

    # Step 4c: incidents preserved
    inc_post = requests.get(f"{BASE_URL}/api/plans/caregiver/{ALEX_ID}/incidents", timeout=15).json()
    post_incidents = inc_post.get("incidents", [])
    assert len(post_incidents) >= len(pre_incidents), f"incidents must be preserved: pre={len(pre_incidents)} post={len(post_incidents)}"

    # Step 4d: idempotent second reset
    reset2 = requests.post(f"{BASE_URL}/api/channel/dev/reset/{ALEX_ID}", headers=MGR, timeout=15)
    assert reset2.status_code == 200
    body2 = reset2.json()
    assert body2.get("refresher_cleared") == 0, f"should be 0: {body2}"
    assert body2.get("drafts_deleted") == 0, f"should be 0: {body2}"


def test_final_cleanup():
    r = requests.post(f"{BASE_URL}/api/channel/dev/reset/{ALEX_ID}", headers=MGR, timeout=15)
    assert r.status_code == 200
