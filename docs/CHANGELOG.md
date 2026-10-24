# FirstShift — Changelog

## Phase 2 — Data + Shell (2026-02-24)

- **POLISH-A**: `POST /api/media` now returns `url` as a relative path
  (`/api/media/<uuid>`). The frontend prepends `REACT_APP_BACKEND_URL`;
  Twilio/callers prepend their own host. `CONTRACTS.md` updated.
- **POLISH-B**: `call_gemini` retries `503 UNAVAILABLE` up to 2 times
  with 1 s then 3 s backoff. On final failure the error propagates and
  `/api/ai/health` returns 503 as before.
- **Seed script** at `backend/seed/seed.py`. Runnable via
  `python -m backend.seed.seed`, auto-run on startup when the
  `agencies` collection is empty. Idempotent (wipes & re-seeds only
  the collections it owns). Content: 2 agencies, 5 caregivers with
  real access codes (`en`/`es`/`tl` mix), 4 clients, 3 full skills
  with steps/checks/quiz/`es`+`tl` translations, reference frames
  uploaded to GridFS, 6 attempts with placeholder clips, 3 signoffs.
- **Access-code generator** at `backend/util/access_code.py`. Alphabet
  omits `0`/`O`/`1`/`I`/`L`. `retry_on_duplicate` wraps insert.
- **Agency shell** (phone-first, warm palette, max-width 480 px): top
  bar with role switch (`localStorage` key `firstshift.agency_role`)
  and a "Caregivers" picker, bottom nav built from the auto-discovered
  manifest sorted by `order`. Seven agency nav entries wired across
  `ops`, `lessons`, `grading`, `questions` features.
- **Caregiver shell** at `/c/:code` (chat-shaped, dark warm palette)
  with name, flag, access code, and a 3-tab bottom nav (Chat /
  Lessons / Ask). `useCaregiver()` exposes `{caregiver, agency, code}`
  via React context. Bad codes render a readable 404 screen with a
  "Back to agency" button; role switch does **not** apply here.
- **New feature: `caregivers`** exposes `GET /api/caregivers/list`
  (picker) and `GET /api/caregivers/by-code/:code` (lookup, 404 on
  miss).
- **Pages** (every one fetches real seed data; no "lorem ipsum"
  fallbacks):
  - Today, New hires, Clients (ops)
  - Skills (lessons) + per-caregiver Lessons view
  - Sign-off, Competency files (grading)
  - Questions (empty-state card)
  - Caregiver Chat, Ask (channel/questions)
- **Design tokens** documented in `CONTRACTS.md` §8. Fonts: Fraunces +
  Public Sans. Base 16 px / tap 44 px / 480 px mobile frame.

### Known non-blockers

- `/api/ai/health` still occasionally returns 503 UNAVAILABLE after
  retries if the Gemini model is deeply overloaded upstream. The
  retry policy keeps the normal case green.

## Phase 1 — Backbone (2026-02-24)

- Backend feature auto-discovery (ops, lessons, grading, questions,
  channel placeholders).
- Frontend feature auto-discovery via `require.context`.
- Service stubs (`grade_clip`, `build_lesson`, `send_message`,
  `answer_question`, `build_plan`) with documented shapes.
- GridFS `MediaStore` + `POST /api/media` + `GET /api/media/{uuid}`.
- `google-genai` Gemini helper + `GET /api/ai/health` (verified
  returning real `{ "color": "teal" }` from a generated test PNG).
- Mongo collections + unique index on `caregivers.access_code`.
- Phone-first base styles.
- `docs/CONTRACTS.md` and `docs/CHANGELOG.md`.
- Committed to `main` as "Phase 1: backbone — auto-discovery, GridFS
  media, Gemini helper, stubs, contracts".
