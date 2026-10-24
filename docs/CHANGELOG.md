# FirstShift — Changelog

## channel + questions (branch `channel/questions`, forked off post-merge main)

- **Replaced the Phase-1 Chat/Ask/Questions placeholders** with real surfaces.
- **Caregiver web chat** at `/c/{access_code}`: polling thread, FSM-driven
  menu → skill → steps-with-frames → quiz → video → grading-result flow,
  all localised to `caregivers.language` (en/es/tl). Replies to free text
  that isn't a menu/quiz number are routed through `answer_question`.
- **`send_message` stub swap** (`services/channel_service.py`): now logs every
  outbound to the `messages` collection; sync signature preserved
  (`send_message(caregiver_id, text, media_url=None) -> dict`). Also exposes
  an `async` variant for the channel's own hot path.
- **`answer_question` stub swap** (`services/questions_service.py`): async
  pipeline prepends existing cards + policies into the Gemini prompt and
  requests `{covered, answer, source_title}`. Not-covered answers land in the
  inbox with `status="waiting_owner"`; a care-manager answer creates a `card`
  so future paraphrases of the same question resolve instantly (verified).
- **Agency Questions inbox** at `/questions`: waiting-first list, detail
  pane with editable textarea + browser `MediaRecorder` voice capture.
  Voice clip POSTs to `/api/questions/transcribe` (Gemini audio input
  via existing `call_gemini`); transcript lands in the textarea editable
  by the manager before saving.
- **Signoff hook** (one shared-line change in
  `backend/features/grading/routes_signoff.py`): after a successful
  `$addToSet` on `cleared_skills`, calls `send_message_async` with
  "You're cleared for &lt;skill title&gt;." in the caregiver's language.
  Only fires when `modified_count` from the update is non-zero (so
  re-adds don't send duplicate chats).
- **Policies seeded** (idempotent, at channel feature startup):
  `"Client refuses care"`, `"Client falls"`, `"Running late to a shift"`.
  **These are developer-written placeholders.** User will revise copy.
- **New collections**: `conversations`, `messages`, `cards`, `policies`.
  Additive fields on `caregivers.phone` (forward-compat with WhatsApp).
  Shapes documented in `docs/merge/channel-questions.md`.
- **WhatsApp deferred**: `channel` fields on `conversations`/`messages`
  kept at `"web"` for now. No Twilio code paths exist on this branch.

### Known non-blockers

- Phase-2 seed-data thinness: `translations.es.checks` and
  `translations.<lang>.quiz` are empty on the Glove-removal / Transfer
  seeds. The chat FSM falls back to English text for check descriptions
  when a translation is missing (new skills published through
  `lessons/record` carry full translations and render in-language).
- The Glove-removal seed has no step `frame_id`s; step bubbles rendered
  through the chat don't show inline images for that skill. Any skill
  recorded via `lessons/record` includes frames.


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
