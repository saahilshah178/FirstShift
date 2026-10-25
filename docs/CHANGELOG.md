# FirstShift — Changelog

## MVP Hardening Pass — Batch 4 (branch `mvp-hardening`, 2026-10)

UX polish, copy pass, content pass. Nine items (#18 – #26) in eight
commits. Chat autoscroll keyed on last-message id (fires only on new
message, not every poll). Questions owner-inbox poll backed off 3s →
10s; detail column uses `md:grid-cols-[22rem_minmax(0,1fr)]` so long
answers no longer overflow; `"Answered (owner)" → "Answered by Care
Manager"` via `sourceLabel()`. Practice list row spacing (`py-3 → py-4`,
`leading-snug`, `whitespace-nowrap` on step count). Caregiver Lessons
`"to do"` chip now flips to `"awaiting sign-off"` when the backend's
new `has_pending_attempt` field is true. Per-step reference-video
playback on `SkillDetailPage.js`: `<video controls playsInline>` + each
step frame becomes a `<button>` that seeks to `step.start` and plays
(test-ids `skill-en-step-play-${n}`). Language flags replaced with
text chips (`English/Español/Tagalog`, new test-id
`caregiver-language`). Spanish `tú` + singular `administradora de
cuidados` convention audited across backend + frontend; pin comment in
`backend/features/questions/pipeline.py`. Tagalog ✓ verified
(JSX-level glyph, survives language switching). `Escape` + backdrop
click close `CaregiverPicker` modal; `aria-labelledby` + explicit X
`aria-label`. SkillsPage rows wrapped in `<Link>` so step/check counts
are tappable. **Lowercase `/c/<code>` redirects to uppercase** via
`navigate(..., { replace: true })`, preserving sub-path + query + hash.
Removed misleading "Back to agency" button on bad-code 404. Double-
fetch audit found zero prod-time double fetches; the dev-only
StrictMode duplicate is documented, no code change. Transfer skill
content pass to v6: c4 flagged `safety_critical: false` and "Nurse" →
"The caregiver"; new c6 (`safety_critical: true`) "Non-skid footwear is
on the patient before they stand." with es/tl translations.

## MVP Hardening Pass — Batch 3 (branch `mvp-hardening`, 2026-10)

Role-based access control. `backend/roles.py` defines
`Role.{CARE_MANAGER, TRAINER, SCHEDULER}`, an `AGENCY_ROLES` frozenset,
and `require_role(allowed)` factory that reads `X-Firstshift-Role` via
`Header(default=None)` and raises 403 with
`{reason: role_required|role_not_allowed, allowed: [...]}` on miss or
mismatch. Gated endpoints (full matrix in `docs/merge/mvp-hardening.md`
and CONTRACTS §11): signoff + question answer/transcribe (Care Manager
only); lesson writes incl. edit/publish/draft/retry/translate (Care
Manager + Trainer); archive/unarchive (Care Manager only). Every GET
and all caregiver-side endpoints remain open. Frontend: `api.js`
request interceptor attaches the header from `localStorage`; response
interceptor on 403 fires the shell-registered `onForbidden(payload)`
→ 403 toast. New `useRole()` hook with capability predicates
(`canSignoff`, `canArchiveSkill`, `canEditSkill`, `canRecordSkill`,
`canAnswerQuestions`). Per-page UI hides/disables mutating controls per
role. `sonner` dropped (yarn/CRA conflict) — native lightweight toast
provider at `frontend/src/shell/Toasts.js`. **Not real auth** — header
is client-declared and trivially forgeable; documented as such.

## MVP Hardening Pass — Batch 2 (branch `mvp-hardening`, 2026-10)

Signoff / competency reconciliation + quiz standardization + lazy edit
idempotency. Signoff send-back path strips orphan clears from
`caregivers.cleared_skills` (fixes "cleared without approved attempt"
drift). Lazy competency guard: a competency row is now only rendered
when the caregiver has at least one approved signoff. Override /
send-back note renders in competency detail with proper spacing. Quiz
count unconstrained — editor adds/removes freely. Quiz choice labels
standardised to `1./2./3.` (removes locale ambiguity vs. `a/b/c`).
Rear camera opens on `<input capture="environment">` for chat video
uploads. `POST /api/lessons/skills/{id}/edit` is lazy + idempotent:
no `lesson_jobs` row is written until the first successful
`PUT /jobs/{id}/draft`. Seeded skills had null step timestamps —
backfilled via a new ffprobe script (`backend/scripts/backfill_seeded_timestamps.py`),
run idempotently. Draft `PUT` body shape pinned in CONTRACTS §1c
(full-replace semantics, must send whole draft). Draft chip spacing +
override chip layout polish. Tester-orphan draft row cleaned by
`backend/scripts/cleanup_orphan_drafts.py` (shipped same batch).

## MVP Hardening Pass — Batch 1 (branch `mvp-hardening`, 2026-10)

Media hardening + content polish. Byte-Range support on
`GET /api/media/{uuid}`: `Content-Length` + `Accept-Ranges: bytes`
headers always, `206 Partial Content` on `Range:` requests (fixes
iOS/Safari seek-while-loading). Backfill script
(`backend/scripts/apply_faststart.py`) rewrites existing stored videos
with `+faststart` so the moov atom sits at the head of the file.
`HEAD /api/media/{uuid}` returns headers-only (client probing).
`DELETE /api/lessons/skills/{id}` archives (soft-delete via `archived:
true`); list endpoint filters archived; `POST /unarchive` restores.
Published-skill dedupe: hard-delete the stale copies + migrate
attempt/signoff `skill_id` references via
`backend/scripts/dedupe_published_skills.py`. Jovelyn's seeded attempt
swapped from a WAV placeholder to a real MP4. Glove-removal content
pass: step frames, quiz text, check translations tightened.

## lessons/record (branch `lessons/record`, forked off main)

Record-a-skill end-to-end pipeline for the Care Manager. **Chunked
upload** (`POST /uploads` → `PUT /uploads/{id}/chunks/{i}` →
`POST /uploads/{id}/complete`) with resumable semantics. **Transcode
stage** uses ffmpeg (HEVC → H.264, +faststart) via `transcode.py` +
ffprobe. **Analyze stage** calls Gemini with the lane-B response schema
(`schemas.py`) and retries on 503. **Draft editor** at
`/skills/drafts/:jobId` with step/check/quiz editing + per-step frame
re-pick. **Publish** bumps the skill `version`, wipes the job rows for
that skill (the published skill IS the audit trail), and queues
es + tl translation. **Translations** are retryable + reviewable
(`POST /skills/{id}/translations/retry`,
`POST /skills/{id}/translations/{lang}/review`). New collection
`lesson_jobs` is owned entirely by this feature. In-process
`runner.py` with heartbeat + stale sweep (no celery). Zero shared-line
changes beyond auto-discovery picking up the new files. Full endpoint
table and state-machine diagram in `docs/merge/lessons.md`.

## grading/signoff (branch `grading/signoff`, forked off main)

Adaptive-3-run `grade_clip` pipeline + sign-off workflow.
`POST /api/grading/clips` ingests multipart mp4, transcodes HEVC →
H.264 via ffmpeg, runs the Gemini video-analysis pipeline up to 3
times (early stop on unanimous pass; consensus merge over inconclusive
runs), writes an `attempts` row with `overall`, `score`, `checks[]`,
`frame_ids[]`, `graded_at`. `POST /attempts/{id}/signoff`
(`{decision: approve|send_back, note}`) updates `caregivers.cleared_skills`
on approve and records a `signoffs` row either way. Competency rollup
at `GET /api/grading/competency`. Caregiver `/practice` + `/practice/:skillId`
UI. Agency `/signoff` queue + `/signoff/:id` detail + `/competency/:id`
drill-in. Idempotent `Glove removal` seed (`backend/features/grading/seed.py`)
runs on feature startup. Stale sweeper flips abandoned `grading` rows
to `grading_error` after 10 min. **`ffmpeg + ffprobe` required** —
`apt-get install -y ffmpeg` on the host (verified 5.1.9). One shared-
line change (`CaregiverLayout` adds `AbortController` to the by-code
fetch) folded in at the end of the branch, documented in
`docs/merge/grading.md`.

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
