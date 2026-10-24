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
  - `cdf59bd` feat(grading): caregiver /practice and agency /signoff UI
  - `66e3bdd` docs(grading): merge notes final
  - `(this commit)` fix(caregiver): restore StrictMode, add AbortController to CaregiverLayout fetch

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

**None net**, after the follow-up fix below. During the branch I did
touch two shared files; the final commit undoes the risky one and
confines the replacement to one caregiver-layout change.

| File                                   | Change                                                                                              | Status                                                                                                                                                                                                                                                                                                                                     |
| -------------------------------------- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `frontend/src/index.js`                | Removed `<React.StrictMode>` in a mid-branch commit; **restored** in the final `fix(caregiver)` commit. | Net: **unchanged** on branch end. No other feature loses StrictMode's dev-time double-invoke signal.                                                                                                                                                                                                                                        |
| `frontend/src/shell/CaregiverLayout.js` | Fetch rewritten to use `AbortController` (axios `signal`). Cancelled errors (`CanceledError` / `ERR_CANCELED` / `AbortError`) are swallowed in `.catch`; genuine 404 / 500 / network errors still surface. | **Final shape** on the branch. This is the proper fix for the StrictMode double-invoke race the mid-branch workaround was papering over. Verified: `/c/2TBAFX` and `/c/2TBAFX/practice` both render under StrictMode with no "setState on unmounted component" warnings; the first mount's fetch is cancelled with `net::ERR_ABORTED` (visible in the browser console) and the second fetch's response populates the layout. |

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

## Known quirks

### Validation order in `POST /api/grading/attempts/{id}/signoff`

Checks fire in this order:

1. attempt exists → 404 if not
2. `reviewed is False` → 409 if already reviewed
3. `status in {ready_to_sign, needs_practice}` → 409 if not signable
4. no newer attempt exists for this caregiver+skill → 409 if there is one
5. decision-specific note-required checks → 422 if a required note is missing

Consequence (tester-flagged): sending `send_back` with an empty note
against an **unsignable** attempt returns **409** ("not signable"),
not 422 ("note required"). This is intentional. The attempt's
signability is a structural precondition — the note rule is only
meaningful when a signoff could actually land. 422 is reachable only
on genuinely signable attempts. If a future consumer wants the 422
to win, we'd need to swap steps 3 and 5, but that would reject
unsignable requests on the wrong axis.

### Test-fixture residue cleaned

Stage-5 curl tests inserted two synthetic signed-off attempts for Alex
Johnson (`2TBAFX`) on the Glove-removal skill, with signer strings
`Rachel Kim, RN` and `Dani Osei`. Those are not Phase-2 seed signers;
they only existed because of in-branch testing and the fact that
`backend/seed/seed.py` does not own the `signoffs` collection for
Phase-3 payloads. The final commit removes those two attempts, their
two signoffs, and the stale `cleared_skills` entry so a tester
spot-checking `GET /api/grading/competency/<alex>` sees the honest
state. Nothing in production code paths changed.
