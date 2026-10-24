"""Translation pipeline (publish-time).

- First publish: build es and tl via Gemini, status "machine".
- Republish: translate only items whose English text changed; keep prior
  translations for unchanged items. Status becomes "machine" if anything
  changed, else keeps prior status. Failures leave status "stale".
"""
from __future__ import annotations

import logging
from typing import Any

from ai.gemini import call_gemini

from .schemas import LANGUAGE_NAMES, TRANSLATE_PROMPT, translate_schema

logger = logging.getLogger("firstshift.lessons.translate")


def _diff_items(english: dict, prior_english: dict | None) -> dict[str, bool]:
    """Compare current English against the previously-published English.

    Returns {'title': bool, 'step:n': bool, 'check:id': bool, 'quiz:id': bool}
    where True means "English text changed; retranslation needed".
    """
    changed: dict[str, bool] = {}
    if prior_english is None:
        changed["title"] = True
        for s in english.get("steps", []):
            changed[f"step:{s['n']}"] = True
        for c in english.get("checks", []):
            changed[f"check:{c['id']}"] = True
        for q in english.get("quiz", []):
            changed[f"quiz:{q['id']}"] = True
        return changed

    changed["title"] = english.get("title") != prior_english.get("title")

    prior_steps = {s["n"]: s for s in prior_english.get("steps", [])}
    for s in english.get("steps", []):
        p = prior_steps.get(s["n"])
        if p is None or p.get("title") != s.get("title") or p.get("instruction") != s.get("instruction"):
            changed[f"step:{s['n']}"] = True

    prior_checks = {c["id"]: c for c in prior_english.get("checks", [])}
    for c in english.get("checks", []):
        p = prior_checks.get(c["id"])
        if p is None or p.get("description") != c.get("description"):
            changed[f"check:{c['id']}"] = True

    prior_quiz = {q["id"]: q for q in prior_english.get("quiz", [])}
    for q in english.get("quiz", []):
        p = prior_quiz.get(q["id"])
        if (
            p is None
            or p.get("prompt") != q.get("prompt")
            or list(p.get("choices") or []) != list(q.get("choices") or [])
        ):
            changed[f"quiz:{q['id']}"] = True

    return changed


def _subset(english: dict, keys_changed: dict[str, bool]) -> dict:
    """Build the subset payload sent to Gemini — only the items that changed."""
    out = {"title": english["title"], "steps": [], "checks": [], "quiz": []}
    for s in english.get("steps", []):
        if keys_changed.get(f"step:{s['n']}"):
            out["steps"].append({"n": s["n"], "title": s["title"], "instruction": s["instruction"]})
    for c in english.get("checks", []):
        if keys_changed.get(f"check:{c['id']}"):
            out["checks"].append({"id": c["id"], "description": c["description"]})
    for q in english.get("quiz", []):
        if keys_changed.get(f"quiz:{q['id']}"):
            out["quiz"].append({"id": q["id"], "prompt": q["prompt"], "choices": list(q.get("choices") or [])})
    return out


def _validate_translation(payload: Any, subset: dict) -> dict | None:
    """Check the translation payload has the exact counts & ids the subset asks for."""
    if not isinstance(payload, dict):
        return None
    steps = payload.get("steps") or []
    checks = payload.get("checks") or []
    quiz = payload.get("quiz") or []
    if not isinstance(steps, list) or not isinstance(checks, list) or not isinstance(quiz, list):
        return None
    if len(steps) != len(subset.get("steps") or []):
        return None
    if len(checks) != len(subset.get("checks") or []):
        return None
    if len(quiz) != len(subset.get("quiz") or []):
        return None
    want_step_ns = [s["n"] for s in subset.get("steps") or []]
    want_check_ids = [c["id"] for c in subset.get("checks") or []]
    want_quiz_ids = [q["id"] for q in subset.get("quiz") or []]
    if [s.get("n") for s in steps] != want_step_ns:
        return None
    if [c.get("id") for c in checks] != want_check_ids:
        return None
    if [q.get("id") for q in quiz] != want_quiz_ids:
        return None
    for q in quiz:
        choices = q.get("choices")
        if not isinstance(choices, list) or len(choices) != 3:
            return None
    return payload


def _merge(english: dict, prior_lang: dict | None, new: dict | None, keys_changed: dict[str, bool]) -> dict:
    """Produce the final translation payload merging prior and new translations.

    Shape:
      {title, steps:[{n,title,instruction}], checks:[{id,description}],
       quiz:[{id,prompt,choices}], status: ...}
    """
    out: dict[str, Any] = {}
    # Title
    if keys_changed.get("title") and new is not None:
        out["title"] = new.get("title") or (english.get("title") or "")
    else:
        out["title"] = (prior_lang or {}).get("title") or english.get("title") or ""

    # Steps
    prior_steps_by_n = {s["n"]: s for s in ((prior_lang or {}).get("steps") or [])}
    new_steps_by_n = {s.get("n"): s for s in (new or {}).get("steps", [])} if new else {}
    merged_steps = []
    for s in english.get("steps", []):
        n = s["n"]
        if keys_changed.get(f"step:{n}") and n in new_steps_by_n:
            src = new_steps_by_n[n]
            merged_steps.append({
                "n": n,
                "title": src.get("title") or s["title"],
                "instruction": src.get("instruction") or s["instruction"],
            })
        elif n in prior_steps_by_n:
            p = prior_steps_by_n[n]
            merged_steps.append({"n": n, "title": p.get("title") or s["title"], "instruction": p.get("instruction") or s["instruction"]})
        else:
            # No prior and translation didn't come back; fall back to english text.
            merged_steps.append({"n": n, "title": s["title"], "instruction": s["instruction"]})
    out["steps"] = merged_steps

    # Checks
    prior_checks_by_id = {c["id"]: c for c in ((prior_lang or {}).get("checks") or [])}
    new_checks_by_id = {c.get("id"): c for c in (new or {}).get("checks", [])} if new else {}
    merged_checks = []
    for c in english.get("checks", []):
        cid = c["id"]
        if keys_changed.get(f"check:{cid}") and cid in new_checks_by_id:
            merged_checks.append({"id": cid, "description": new_checks_by_id[cid].get("description") or c["description"]})
        elif cid in prior_checks_by_id:
            merged_checks.append({"id": cid, "description": prior_checks_by_id[cid].get("description") or c["description"]})
        else:
            merged_checks.append({"id": cid, "description": c["description"]})
    out["checks"] = merged_checks

    # Quiz
    prior_quiz_by_id = {q["id"]: q for q in ((prior_lang or {}).get("quiz") or [])}
    new_quiz_by_id = {q.get("id"): q for q in (new or {}).get("quiz", [])} if new else {}
    merged_quiz = []
    for q in english.get("quiz", []):
        qid = q["id"]
        if keys_changed.get(f"quiz:{qid}") and qid in new_quiz_by_id:
            src = new_quiz_by_id[qid]
            merged_quiz.append({
                "id": qid,
                "prompt": src.get("prompt") or q["prompt"],
                "choices": [str(x) for x in (src.get("choices") or q.get("choices") or [])],
            })
        elif qid in prior_quiz_by_id:
            p = prior_quiz_by_id[qid]
            merged_quiz.append({"id": qid, "prompt": p.get("prompt") or q["prompt"], "choices": [str(x) for x in (p.get("choices") or q.get("choices") or [])]})
        else:
            merged_quiz.append({"id": qid, "prompt": q["prompt"], "choices": list(q.get("choices") or [])})
    out["quiz"] = merged_quiz
    return out


async def translate_language(
    *,
    english: dict,
    prior_english: dict | None,
    prior_lang: dict | None,
    lang: str,
) -> tuple[dict, str]:
    """Translate English content → {es|tl}; returns (payload, status).

    - `english`       — the new English payload we're publishing.
    - `prior_english` — the English payload from the previously-published skill
                        (None on first publish). Used to detect which items changed.
    - `prior_lang`    — the previously-published translation (None on first publish).
                        Reused for items whose English didn't change.

    status ∈ {"machine", "reviewed", "stale"}.
    - "machine": at least one item was (re)translated this call.
    - "reviewed": nothing changed and prior status was reviewed.
    - "stale": translation attempt failed.
    """
    keys_changed = _diff_items(english, prior_english)
    anything_changed = any(keys_changed.values())
    if not anything_changed:
        # Nothing to do; preserve prior status (default "machine").
        prior_status = (prior_lang or {}).get("status") or "machine"
        merged = _merge(english, prior_lang, None, keys_changed)
        return merged, prior_status

    subset = _subset(english, keys_changed)
    prompt = TRANSLATE_PROMPT.format(lang_name=LANGUAGE_NAMES[lang])
    prompt += "\n\nSource JSON:\n" + _as_json(subset)
    schema = translate_schema()

    try:
        raw = await call_gemini(prompt=prompt, media_uuids=[], response_schema=schema)
        validated = _validate_translation(raw, subset)
        if validated is None:
            # Retry once appending the error so Gemini self-corrects.
            raw2 = await call_gemini(
                prompt=prompt + "\n\nPrevious response was invalid (count or id mismatch). Return exactly the counts and ids from the source JSON.",
                media_uuids=[],
                response_schema=schema,
            )
            validated = _validate_translation(raw2, subset)
        if validated is None:
            logger.warning("translation to %s failed validation; marking stale", lang)
            merged = _merge(english, prior_lang, None, keys_changed)
            return merged, "stale"
        merged = _merge(english, prior_lang, validated, keys_changed)
        return merged, "machine"
    except Exception as exc:  # noqa: BLE001
        logger.exception("translation to %s raised: %s", lang, exc)
        merged = _merge(english, prior_lang, None, keys_changed)
        return merged, "stale"


def _as_json(obj: Any) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, indent=2)
