"""Lane-B Gemini schema + validators for the lessons pipeline.

Keep every schema/prompt change here so the pipeline module stays short.
"""
from __future__ import annotations

from typing import Any

# ---------- Lane-B prompt ----------
LANE_B_PROMPT = (
    "Use only what the nurse shows or says. Each instruction is under 20 "
    "words, in plain language. Checks must be visible on camera, in order, "
    "ids c1..cN. The quiz is a short set of 1 to 3 multiple-choice questions, "
    "each with 3 options; answer is the index."
)


def analyze_prompt(duration_s: float) -> str:
    """Compose the full analyze prompt with the video duration appended."""
    return LANE_B_PROMPT + f" The video is {duration_s:.1f} seconds long."


# ---------- Gemini response schema (lane-B) ----------
# Values match the brief exactly: title, steps[{n,title,instruction,start,end}],
# checks[{id,description,safety_critical}], quiz[{q,options[3],answer}].
LANE_B_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "title": {"type": "string"},
                    "instruction": {"type": "string"},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                },
                "required": ["n", "title", "instruction", "start", "end"],
            },
        },
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "description": {"type": "string"},
                    "safety_critical": {"type": "boolean"},
                },
                "required": ["id", "description", "safety_critical"],
            },
        },
        "quiz": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "q": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "answer": {"type": "integer"},
                },
                "required": ["q", "options", "answer"],
            },
        },
    },
    "required": ["title", "steps", "checks", "quiz"],
}


# ---------- Translation schema ----------
TRANSLATE_PROMPT = (
    "Translate the following nursing-skill lesson into {lang_name}. "
    "Keep ids and the step number `n` exactly. Each step instruction stays "
    "under 20 words. Return JSON matching the schema. Do not drop or add "
    "any step, check or quiz item. Translate every text field."
)

LANGUAGE_NAMES = {"es": "Spanish", "tl": "Tagalog"}


def translate_schema() -> dict[str, Any]:
    """Schema for a {es|tl} translation payload."""
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "n": {"type": "integer"},
                        "title": {"type": "string"},
                        "instruction": {"type": "string"},
                    },
                    "required": ["n", "title", "instruction"],
                },
            },
            "checks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["id", "description"],
                },
            },
            "quiz": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "prompt": {"type": "string"},
                        "choices": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["id", "prompt", "choices"],
                },
            },
        },
        "required": ["title", "steps", "checks", "quiz"],
    }


# ---------- Timestamp parsing ----------
def parse_timestamp(s: Any) -> float | None:
    """Parse 'm:ss.s' / 'ss.s' / numeric to float seconds. None on failure."""
    if isinstance(s, (int, float)):
        return float(s)
    if not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None
    try:
        if ":" in s:
            m, rest = s.split(":", 1)
            return float(m) * 60.0 + float(rest)
        return float(s)
    except (ValueError, TypeError):
        return None


# ---------- Validation of Gemini output against the draft contract ----------
def validate_analyze(
    payload: dict, duration_s: float
) -> tuple[dict, list[dict]]:
    """Validate+normalize the Gemini analyze response.

    Returns (normalized_draft, problems).
    `problems` is a list of {where, message, blocking}.
    A "blocking" problem means the draft is unsafe to publish without a fix,
    but it is still returned so the manager can edit.
    """
    problems: list[dict] = []

    title = str(payload.get("title") or "").strip() or "Untitled skill"

    # ---- Steps ----
    raw_steps = payload.get("steps") or []
    if not isinstance(raw_steps, list) or not raw_steps:
        problems.append({"where": "steps", "message": "No steps generated.", "blocking": True})

    steps_out: list[dict] = []
    prev_end = 0.0
    for i, raw in enumerate(raw_steps or []):
        if not isinstance(raw, dict):
            problems.append({"where": f"steps[{i}]", "message": "Step is not an object.", "blocking": True})
            continue
        n = raw.get("n")
        if not isinstance(n, int) or n != i + 1:
            problems.append({
                "where": f"steps[{i}].n",
                "message": f"Expected n={i+1}, got {n!r}; auto-renumbered.",
                "blocking": False,
            })
            n = i + 1
        start = parse_timestamp(raw.get("start"))
        end = parse_timestamp(raw.get("end"))
        if start is None or end is None:
            problems.append({
                "where": f"steps[{i}]",
                "message": "Could not parse start/end timestamps.",
                "blocking": True,
            })
            start = start if start is not None else prev_end
            end = end if end is not None else min(duration_s, start + 1.0)
        if start < 0 or end > duration_s + 0.25 or start >= end:
            problems.append({
                "where": f"steps[{i}]",
                "message": f"Timestamps out of range (0 ≤ {start:.2f} < {end:.2f} ≤ {duration_s:.2f}).",
                "blocking": True,
            })
            start = max(0.0, min(start, duration_s - 0.1))
            end = max(start + 0.1, min(end, duration_s))
        instr = str(raw.get("instruction") or "").strip()
        if len(instr.split()) >= 20:
            problems.append({
                "where": f"steps[{i}].instruction",
                "message": "Instruction is 20+ words — consider shortening.",
                "blocking": False,
            })
        steps_out.append({
            "n": n,
            "title": str(raw.get("title") or "").strip() or f"Step {n}",
            "instruction": instr,
            "start": round(start, 2),
            "end": round(end, 2),
            "frame_id": None,
        })
        prev_end = end

    # In-order check
    for i in range(1, len(steps_out)):
        if steps_out[i]["start"] + 0.001 < steps_out[i - 1]["start"]:
            problems.append({
                "where": f"steps[{i}]",
                "message": "Steps are not in chronological order.",
                "blocking": True,
            })
            break

    # ---- Checks ----
    # Preserve existing check IDs (TWEAK-B / Batch-2 tightening): a skill
    # may legitimately use a non-`c{N}` prefix (seeded Glove removal is
    # `g1..g7` and attempt records already reference those ids — renaming
    # would orphan them). The validator still prefers `c{N}` for new,
    # pipeline-authored skills; it only flags a non-standard id as an
    # informational problem on the editor path.
    raw_checks = payload.get("checks") or []
    checks_out: list[dict] = []
    if not isinstance(raw_checks, list) or not raw_checks:
        problems.append({"where": "checks", "message": "No checks generated.", "blocking": True})
    for i, raw in enumerate(raw_checks or []):
        if not isinstance(raw, dict):
            problems.append({"where": f"checks[{i}]", "message": "Check is not an object.", "blocking": True})
            continue
        want_id = f"c{i+1}"
        got_id = raw.get("id")
        if isinstance(got_id, str) and got_id.strip():
            final_id = got_id.strip()
            if final_id != want_id:
                problems.append({
                    "where": f"checks[{i}].id",
                    "message": f"Non-standard id {final_id!r} preserved (new skills prefer {want_id!r}).",
                    "blocking": False,
                })
        else:
            problems.append({
                "where": f"checks[{i}].id",
                "message": f"Missing id; assigned {want_id!r}.",
                "blocking": False,
            })
            final_id = want_id
        checks_out.append({
            "id": final_id,
            "description": str(raw.get("description") or "").strip() or "(no description)",
            "safety_critical": bool(raw.get("safety_critical", False)),
        })

    # ---- Quiz ----
    # Fix #10 — quiz count is unconstrained; 0..N allowed. Still enforce
    # 3 choices and a valid answer index per question that IS present.
    raw_quiz = payload.get("quiz") or []
    quiz_out: list[dict] = []
    if raw_quiz and not isinstance(raw_quiz, list):
        problems.append({
            "where": "quiz",
            "message": "Quiz must be a list.",
            "blocking": True,
        })
        raw_quiz = []
    for i, raw in enumerate(raw_quiz or []):
        if not isinstance(raw, dict):
            problems.append({"where": f"quiz[{i}]", "message": "Quiz item is not an object.", "blocking": True})
            continue
        options = raw.get("options") or raw.get("choices") or []
        if not isinstance(options, list) or len(options) != 3:
            problems.append({
                "where": f"quiz[{i}].options",
                "message": f"Expected 3 options, got {len(options) if isinstance(options, list) else 0}.",
                "blocking": True,
            })
            options = (list(options) if isinstance(options, list) else []) + ["?"] * 3
            options = options[:3]
        answer = raw.get("answer")
        if not isinstance(answer, int) or answer < 0 or answer > 2:
            problems.append({
                "where": f"quiz[{i}].answer",
                "message": f"answer_index must be 0..2 (got {answer!r}).",
                "blocking": True,
            })
            answer = 0 if not isinstance(answer, int) else max(0, min(2, answer))
        prompt = raw.get("prompt") or raw.get("q") or ""
        quiz_out.append({
            "id": f"q{i+1}",
            "prompt": str(prompt).strip() or f"Question {i+1}",
            "choices": [str(o).strip() for o in options],
            "answer_index": answer,
        })

    draft = {
        "title": title,
        "steps": steps_out,
        "checks": checks_out,
        "quiz": quiz_out,
    }
    return draft, problems


def blocking_problems(problems: list[dict]) -> list[dict]:
    return [p for p in problems if p.get("blocking")]
