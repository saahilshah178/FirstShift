# Merge notes — `grading/signoff`

> Final document; closes the feature branch.

## Branch

- `grading/signoff` off `main` at `6f18729`.
- Commit chain (oldest first):
  - `642d0eb` chore(grading): ffmpeg system dep + merge notes skeleton
  - `632b113` feat(grading): seed Glove removal skill (idempotent) + grade_clip stub swap
  - `a53911f` feat(grading): clip upload + HEVC->H.264 transcode + attempt stub
  - `b788fa9` feat(grading): adaptive 3-run grade_clip pipeline + background job
  - `715f3a9` feat(grading): signoff + competency endpoints
  - `(stage 6 commit)` feat(grading): caregiver /practice and agency /signoff UI
  - `(this commit)` docs(grading): merge notes final

## System dependencies

- **ffmpeg + ffprobe** (`apt-get install -y ffmpeg` on the preview
  container; verified `ffmpeg 5.1.9`, `ffprobe 5.1.9`). Production
  images must include ffmpeg in the base layer; without it,
  `POST /api/grading/clips` returns `415` (ffprobe decode fails).

## Env

- `GEMINI_API_KEY` — unchanged, required by `backend/ai/gemini.py`.
- `GEMINI_MODEL` — already env-driven in `backend/ai/gemini.py` since
  Phase 1 (default `gemini-3.5-flash`). This branch adds the key
  **explicitly** to `backend/.env` for operator visibility. The
  default value is unchanged.

## Shared-line changes

Only one. The feature brief said "expect zero" — flagging explicitly:

| File                           | Change                                                                                                                                                                                                  | Why                                                                                                                                                                                                                                                                                                                                                                     |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `frontend/src/index.js`        | Removed the `<React.StrictMode>` wrapper around `<App />`.                                                                                                                                              | React 19 StrictMode's dev-only double-invoke of `useEffect` was leaving `CaregiverLayout` stuck in `status: "loading"` after the second mount's abort flag closed. Phase 2 lived with the race because the first fetch *usually* resolved before cleanup; adding another caregiver-side feature (`Practice`) made the race hit every time. Production builds don't double-invoke, so this change does not affect release behaviour. Revisiting via `AbortController` is tracked below. |

## Files added

Backend:
- `backend/features/grading/seed.py` — idempotent Glove-removal skill seed.
- `backend/features/grading/pipeline.py` — Lane-B adaptive 3-run pipeline + prompt + schema.
- `backend/features/grading/ingest.py` — clip validate + transcode + attempt create.
- `backend/features/grading/background.py` — asyncio background grading job + stale sweeper.
- `backend/features/grading/routes_signoff.py` — queue / signoff / per-caregiver competency / full-skill routes.
- `docs/merge/grading.md` — this file.

Frontend:
- `frontend/src/features/grading/PracticePage.js`
- `frontend/src/features/grading/PracticeResultPage.js`
- `frontend/src/features/grading/SignoffDetailPage.js`
- `frontend/src/features/grading/CompetencyDetailPage.js`

Non-shared edits inside my allowed areas:
- `backend/services/grading_service.py` — stub body swapped to call the
  pipeline (signature preserved; now `async def`).
- `backend/features/grading/__init__.py` — added upload / list / poll /
  regrade / competency placeholder; wires background job and startup
  tasks (seed, stale sweeper).
- `frontend/src/features/grading/routes.js` — real routes + new
  `Practice` caregiver nav entry.
- `frontend/src/features/grading/SignoffPage.js` — upgraded Phase-2
  list to tabbed queue view.
- `frontend/src/features/grading/CompetencyPage.js` — added `Link` to
  per-caregiver detail.
- `docs/CONTRACTS.md` — four new TODO entries under §10.

## New endpoints (all under `/api/grading`)

| Verb | Path                                | Shape                                                                                                                           |
| ---- | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| POST | `/clips`                            | multipart `file`, `skill_id`, `caregiver_id` → `{attempt_id, clip_id, status:"grading"}`. 413 >100 MB, 415 undecodable, 422 duration out of 3–45 s. |
| GET  | `/attempts`                         | Phase-2 shape, additive `status`/`verdict`/`score`/`runs_used`/`graded_once`/`reviewed` fields. Query: `caregiver_id`, `status`. |
| GET  | `/attempts/{id}`                    | Full attempt doc (public projection) with `.signoff` if present.                                                                 |
| POST | `/attempts/{id}/regrade`            | Resets status to `grading`, re-enqueues; 409 if `reviewed`.                                                                      |
| GET  | `/queue`                            | `{ready_to_sign:[], needs_practice:[]}`, excludes reviewed / retake / grading / errored.                                        |
| POST | `/attempts/{id}/signoff`            | Body `{decision:"approve"\|"send_back", signer, signer_role, note}`. 409 if already reviewed / not signable / not latest. 422 if `send_back` without note or `approve` of a failed verdict without note. |
| GET  | `/competency/{caregiver_id}`        | Per-caregiver file: every skill with `cleared`/`not_cleared`/`not_attempted`, latest attempt summary, full history.             |
| GET  | `/skill/{skill_id}`                 | Full skill doc (steps + translations) consumed by the Practice UI.                                                              |

Phase-2 shapes left unchanged (additive fields only):
- `GET /api/grading/attempts`
- `GET /api/grading/competency`

Verified against `/api/openapi.json` — every endpoint listed.

## New fields and defaults

### `attempts`

| field                   | default        |
| ----------------------- | -------------- |
| `status`                | `"grading"`    |
| `verdict`               | `null`         |
| `score`                 | `null`         |
| `message_for_caregiver` | `""`           |
| `runs_used`             | `0`            |
| `graded_once`           | `false`        |
| `raw_runs`              | `[]`           |
| `frame_ids`             | `[]`           |
| `error`                 | `null`         |
| `reviewed`              | `false`        |
| `duration`              | computed       |
| `checks[].note`         | `""`           |
| `checks[].safety_critical` | `false`     |
| `checks[].description`  | `""`           |

Legal `status` values: `"grading"`, `"ready_to_sign"`,
`"needs_practice"`, `"retake_required"`, `"grading_error"`.

### `signoffs`

| field          | default        |
| -------------- | -------------- |
| `decision`     | `"approve" \| "send_back"` (required) |
| `override`     | `false`        |
| `signer_role`  | `""`           |

## Idempotency

- `backend/seed/seed.py` (Phase-2) wipes the `skills` collection on
  every run. The grading feature's own seed runs on every startup via
  `asyncio.create_task` at import time, so one `python -m
  backend.seed.seed` + a backend restart repopulates everything,
  Glove removal included.
- Approve endpoint uses `$addToSet` on `caregivers.cleared_skills`;
  repeated approvals of the same (caregiver, skill) are idempotent at
  the Mongo layer and 409 at the HTTP layer.

## Stale sweeper

`features/grading/background.py::mark_stale_grading` flips any attempt
with `status: "grading"` older than 10 minutes to `grading_error`.
Fired at feature-import (startup) and inline on each read in
`GET /attempts` / `GET /attempts/{id}`.

## Manual test plan

Preconditions:
- A caregiver access code — any from `GET /api/caregivers/list`.
  Tester handoff: see `/app/memory/test_credentials.md`.
- The Glove-removal skill id can be fetched with:
  ```bash
  curl -s "$BASE/api/lessons/skills" \
    | python -c "import sys,json; [print(s['id']) for s in json.load(sys.stdin)['skills'] if s['title']=='Glove removal']"
  ```

Curl checks (user-supplied clips, tolerance ±1 s):

1. **Planted-mistake clip** at second T:
   ```bash
   curl -F "file=@mistake.mp4" -F "skill_id=$SKILL" \
        -F "caregiver_id=$CG" $BASE/api/grading/clips
   # → {attempt_id, clip_id, status:"grading"}
   curl $BASE/api/grading/attempts/$AID    # poll ~every 3 s
   ```
   Expected: a check for the planted mistake has `result:"fail"` or
   `"unclear"` at a `time` within T±1 s; `/signoff/$AID` renders a
   marker at that offset.
2. **Corrected clip**: upload, poll. Expected: `verdict:"pass"`,
   `status:"ready_to_sign"`.
3. **Approve** the pass:
   ```bash
   curl -X POST $BASE/api/grading/attempts/$AID/signoff \
        -H "Content-Type: application/json" \
        -d '{"decision":"approve","signer":"RN Rachel","signer_role":"Care Manager","note":""}'
   ```
   Expected: `caregivers.cleared_skills` contains the Glove skill;
   `GET /competency/$CG` shows the skill as `cleared` with signer, date
   and clip; a second approve returns `409`.
4. **Duration guard**: upload a 50 s clip → `422`.
5. **Safety miss**: upload a clip that misses `g1` or `g4` → logs show
   adaptive runs 2 and 3 fired; attempt has `runs_used: 3`.
6. **Seed idempotency**: `python -m backend.seed.seed` + restart
   backend. Expect Glove-removal skill re-created with the same shape;
   caregivers / clients / attempts seeded by phase-2 seed are intact.

Preflight (as the orchestration brief required):
- `curl $BASE/api/ai/health` returned `{"ok":true,"model":"gemini-3.5-flash","result":{"color":"teal"}}` at the start of this branch and immediately after the stage-7 commit.

## Known non-blockers

- Gemini free-tier quota (20 requests/day) was briefly exhausted
  during stage-4 end-to-end testing. The pipeline tolerated it — one
  of three adaptive runs failed with `429 RESOURCE_EXHAUSTED` and the
  remaining two met the ≥2-valid-run bar. Operators moving to paid
  tier should see this scenario disappear.
- `index.js` StrictMode removal — see §Shared-line changes. Track as
  P1: swap useEffect fetches to `AbortController` + reinstate
  StrictMode in a follow-up.
