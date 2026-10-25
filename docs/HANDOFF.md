# FirstShift — Handoff

> **Target reader**: an orchestrator agent in a fresh Emergent job that just
> cloned this repo and has **zero** prior context. Read this + `CONTRACTS.md`
> + the latest `docs/merge/<fork>.md` and you can make good decisions.

## A. What this is

FirstShift is a **phone-first web app for a home-care agency**: caregivers
chat with the app via a short `/c/<code>` URL to learn skills (reference
video → steps → quiz → record their own attempt) and ask free-text
questions; agency staff grade attempts, sign-off competency, and answer
anything the AI could not. The problem it solves is **getting new
caregivers client-ready faster** than classroom training allows, with
auditable sign-off trails and a translation-first UX (en / es / tl).

## B. Stack + how to run

- **Backend**: FastAPI + Motor (async MongoDB). All routes under `/api`.
  Served on `0.0.0.0:8001` by supervisor. Hot-reload on save.
- **Frontend**: **CRA React** (NOT Vite). Auto-discovery uses
  `require.context` from webpack. Served on `3000` by supervisor.
- **DB**: MongoDB, name defaults to `firstshift` (`MONGO_URL` + `DB_NAME`
  from `backend/.env`).
- **AI**: Gemini via `google-genai` SDK on a **paid key**. Default model
  `gemini-3.5-flash` (override via `GEMINI_MODEL`). The Universal
  (Emergent) key was tried in Phase 1 and does **not** cover video
  uploads — the real `GEMINI_API_KEY` is required.
- **System deps**: `ffmpeg` + `ffprobe` (`apt-get install -y ffmpeg`).
  Verified `ffmpeg 5.1.9`. **Not baked into pod snapshots** — see §G.
- **Env vars** (in `backend/.env`):
  - `MONGO_URL`, `DB_NAME` (set, do not touch)
  - `GEMINI_API_KEY`, `GEMINI_MODEL`
  - `CORS_ORIGINS` (defaults to `*`)
  - `LESSONS_FORCE_FAIL_STAGE` — **test-only**. Values:
    `transcode`, `analyze`, `publish` (or empty). Forces the lessons
    pipeline to fail at that stage. Unset in prod.
- **Env vars** (in `frontend/.env`):
  - `REACT_APP_BACKEND_URL` — do not touch; the ingress maps `/api/*`
    through this.
- **Preview URL**: `https://shift-backbone.preview.emergentagent.com`
  (serves the production bundle; dev HMR runs internally only).
- **Supervisor restart** (only after `.env` or dependency changes):
  `sudo supervisorctl restart backend` / `restart frontend`.

## C. Repo structure — the fork-safety contract

The core design is **zero shared registries**. Every feature folder
auto-discovers; branches never need to edit a central file.

### Backend auto-discovery

`backend/server.py` walks `backend/features/` with `pkgutil.iter_modules`
and imports every subpackage. If the subpackage exposes module-level
`router: APIRouter`, it is mounted at `/api/<folder_name>`. Import
failures are logged and **skipped** — never crash the app.

### Frontend auto-discovery

`frontend/src/featureRegistry.js` uses
`require.context('./features', true, /\/routes\.js$/)` to collect every
`routes.js`. Each exports `routes[]` (React-Router patterns) and `nav[]`
(bottom-nav entries). Routes starting with `/c/:code` mount under
`<CaregiverLayout>`; everything else under `<AgencyShell>`.

### Rules a new fork MUST follow

- Add new work inside `backend/features/<name>/` and
  `frontend/src/features/<name>/` only.
- The **only** shared file a fork is expected to touch is its own stub
  in `backend/services/<name>_service.py`.
- Any other shared-line change (e.g. editing `server.py`, `App.css`,
  another feature's folder) MUST be listed in that fork's
  `docs/merge/<name>.md` under "Shared-line changes" with a reason.
- **If anyone adds `backend/registry.py` or a flat `frontend/src/routes.js`,
  that's a regression** — the auto-discovery contract is broken.

### Service-stub wiring state

Each `backend/services/*.py` was Phase-1 fake data; forks swap the body
to call `backend/ai/gemini.py::call_gemini`. Current state:

| Stub              | State                            | Owner feature |
| ----------------- | -------------------------------- | ------------- |
| `grade_clip`      | **WIRED** (adaptive 3-run)       | grading       |
| `build_lesson`    | **WIRED** (full lane-B pipeline) | lessons       |
| `send_message`    | **WIRED** (logs to `messages`)   | channel       |
| `answer_question` | **WIRED** (Gemini + policies + cards) | questions |
| `build_plan`      | **MOCKED** (fake return data)    | ops *(not built yet)* |

## D. Feature-folder status

### `ops` — placeholder

Pages exist (`Today`, `New hires`, `Clients`) and fetch real seed data
via `GET /api/ops/caregivers?sort=hired_at_desc` and `GET /api/ops/clients`.
There is **no business logic** — no shift scheduling, no staffing match,
no new-hire voice intake. `build_plan` is still the fake stub.

### `lessons` — shipped

Record-a-skill pipeline is fully wired (upload → transcode → analyze →
draft editor → publish → es/tl translate). Backend owns `lesson_jobs`
collection, chunked uploads, in-process `runner.py`, and lane-B Gemini
schema. Skill endpoints: `GET /skills`, `GET /skills/{id}`,
`POST /skills/{id}/edit` (lazy, idempotent), `POST /skills/{id}/unarchive`,
`DELETE /skills/{id}` (archive). Job endpoints under
`/api/lessons/jobs/{id}/{draft|publish|retry|steps/{n}/frame}`.
See `docs/merge/lessons.md` for the full endpoint table + state machine.

### `grading` — shipped

`POST /api/grading/clips` ingests mp4 (HEVC → H.264 transcode via ffmpeg),
runs the adaptive 3-pass grade pipeline (Gemini video analysis, consensus
over runs, early stop on unanimous pass), and writes an `attempts` row
with `overall`, `score`, `checks[]`, and `frame_ids[]`. Sign-off endpoint:
`POST /api/grading/attempts/{id}/signoff` with
`{decision: approve|send_back, note}`. Competency rollup at
`GET /api/grading/competency`. Caregiver `/practice` + agency
`/signoff` + `/competency/:id` UIs are shipped.

### `questions` — shipped

Caregiver-side: `POST /api/questions/ask` runs the question through
`answer_question` which prepends existing `cards` + `policies` into the
Gemini prompt. Covered → auto-answered + card reused. Not covered →
row lands in agency inbox with `status="waiting_owner"`. Agency inbox at
`GET /api/questions/inbox` (waiting first), owner answers via
`POST /api/questions/{id}/answer` with body `{text: "..."}`
(**note: field is `text`, not `answer`** — pinned in CONTRACTS §1b).
Voice capture: `POST /api/questions/transcribe` (Gemini audio input).

### `channel` — shipped (web only)

Caregiver web chat lives at `/c/<code>` with FSM-driven menu → skill →
steps-with-frames → quiz → video upload → grading-result flow, localised
to the caregiver's language. State persists in the `conversations`
collection; thread polling via `GET /api/channel/messages/{caregiver_id}`.
After grading signoff, a hook posts "You're cleared for <skill>" into
the thread. **WhatsApp is deferred** — the `channel` field on
`conversations` / `messages` is kept at `"web"` for forward-compat; no
Twilio code exists.

### `caregivers` — thin lookup

`GET /api/caregivers/list` (picker) and
`GET /api/caregivers/by-code/{code}` (lookup, 404 on miss, code
normalised to upper on the server). Everything else about caregivers
lives on `caregivers` records inside the agency features.

## E. Current branch state

- **Active branch**: `mvp-hardening`
- **Top commit at handoff time**: see the `git log` of this commit (the
  one that introduced `HANDOFF.md`).
- **Pod-local `main` reconstructed via local merges**. The pod has no
  `origin` remote; GitHub pushes go through the **Save-to-GitHub** UI,
  not `git push`. GitHub's `main` has the same content via PR merges
  but different SHAs. **Always use "Create Branch & Push". Never Force
  Push.**
- **Four merged forks on pod-local `main`** (each has its own merge note):
  - `grading/signoff` → `docs/merge/grading.md`
  - `lessons/record` → `docs/merge/lessons.md`
  - `channel/questions` → `docs/merge/channel-questions.md`
  - `mvp-hardening` (open) → `docs/merge/mvp-hardening.md`

## F. Phase / batch history (one-liner each)

- **Phase 1 — Backbone (2026-02)**: scaffolding, backend + frontend
  auto-discovery, GridFS `MediaStore` + `POST /api/media`, Gemini
  helper + `/api/ai/health`, five service stubs with documented shapes,
  10 Mongo collections, phone-first base styles, `CONTRACTS.md` seed.
- **Phase 2 — Data + Shell (2026-02-24)**: idempotent `seed.py`
  (2 agencies, 5 caregivers with real access codes, 4 clients, 3 full
  skills with translations, 6 attempts, 3 signoffs), agency shell (role
  switch, caregiver picker, bottom nav from the manifest), caregiver
  shell at `/c/:code`, `caregivers` lookup feature, every page fetches
  real seed (no lorem). POLISH-A: `/api/media` returns relative `url`.
  POLISH-B: `call_gemini` retries 503 twice (1s, 3s).
- **Grading fork (`grading/signoff`)**: adaptive 3-run `grade_clip`
  Gemini pipeline, HEVC→H.264 transcode, Glove-removal seed (idempotent),
  sign-off + competency + /practice + /signoff + /competency/:id UIs,
  stale sweeper for `grading` rows that die silently.
- **Lessons fork (`lessons/record`)**: Record-a-skill end-to-end —
  chunked upload → transcode → Gemini analyze with lane-B schema →
  draft editor → publish (bumps `version`) → es/tl translate pipeline;
  `lesson_jobs` collection owned by this feature; lazy `edit-<skill_id>`
  handles via `POST /skills/{id}/edit`; post-publish wipe of job rows.
- **Channel + Questions fork (`channel/questions`)**: FSM web chat,
  `send_message` + `answer_question` stub swaps, agency inbox with
  voice capture (`/transcribe` via Gemini audio), signoff → chat hook,
  seeded `policies`. WhatsApp deferred; `channel` fields reserved.
- **MVP Hardening Pass** (4 batches, all on `mvp-hardening`):
  - **Batch 1** — media hardening: `+faststart` backfill for stored
    videos, Content-Length + Accept-Ranges + 206 Range responses,
    HEAD support, published-skill dedupe, archive endpoint, Jovelyn's
    attempt swapped from WAV → real MP4, Glove removal content pass.
  - **Batch 2** — signoff/competency reconciliation + quiz
    standardization: orphan clears stripped, lazy competency guard,
    override/send-back note render, quiz count unconstrained + 1./2./3.
    labels, lazy Edit idempotency, rear-camera for video uploads, seed
    timestamp backfill via ffprobe, draft `/PUT` shape pinned.
  - **Batch 3** — real role gating: backend `X-Firstshift-Role` header
    + `require_role` decorator (`backend/roles.py`), per-endpoint allow
    sets, frontend interceptor + per-role UI gating + 403 toast via
    native `Toasts.js` (sonner dropped). **Client-declared, not auth.**
  - **Batch 4** — UX polish: chat autoscroll on new-message only,
    questions poll backoff 3→10s, lessons/practice copy + chip states
    (`has_pending_attempt` → "awaiting sign-off"), per-step reference
    video playback on skill detail, language flags → text labels,
    Spanish `tú` consistency pin, Tagalog ✓ verified, Esc/backdrop/
    whole-card tap a11y, lowercase `/c/<code>` → uppercase redirect
    with `replace:true`, double-fetch audit (StrictMode dev-only),
    bed-to-chair content pass (Transfer v6, new c6 safety-critical).

## G. Known quirks + traps (read before coding)

- **`X-Firstshift-Role` is client-declared and trivially forgeable.**
  It's a UX gate + server-side 403 against accidental misuse, NOT a
  security boundary. Real auth replaces it when it lands
  (CONTRACTS §10).
- **Media is public by UUID** (Twilio-pattern requirement from Phase 1).
  Signed, short-lived tokens are a TODO; the stable integration point
  is the `url` field, not the raw UUID path.
- **Glove removal uses check ids `g1..g7`** while other skills use
  `c1..cN`. **Do NOT rename** — attempts reference them. Different
  prefix is a seed artifact, not a bug.
- **Transfer skill TWEAK-B rule**: pre-v6 attempts reference `c1..c5`
  only; `c6` (non-skid footwear safety-critical) only appears on v6+
  attempts. Any migration that renames existing check ids breaks
  historical attempt rendering.
- **ffmpeg is NOT in the pod snapshot.** After any snapshot restore,
  run `apt-get update && apt-get install -y ffmpeg` or the lessons +
  grading pipelines crash silently (`POST /api/grading/clips` returns
  415; lessons jobs fail at the transcode stage).
- **CRA + StrictMode double-fetch in dev**. Dev-only (`yarn start`);
  the production bundle served from the preview URL fetches once. If
  anyone grep's `useEffect`+`api.get` and counts the network tab in
  dev, they will panic unnecessarily.
- **Pod has no `origin` remote.** `git push` won't work. GitHub pushes
  go through the Emergent "Save to GitHub" UI as a branch push.
- **`/c/:code` sub-routes are limited.** Known good: `/chat` (default),
  `/lessons`, `/ask`, `/practice`, `/practice/<skill_id>`. Any other
  sub-path currently 404s inside the caregiver shell. The uppercase
  redirect in `CaregiverLayout.js` preserves whatever sub-path is sent.
- **Seeded skills had null step timestamps** until the Batch-2 ffprobe
  backfill (`backend/scripts/backfill_seeded_timestamps.py`). New skills
  from `lessons/record` always carry real timestamps. If you add a new
  seeded skill, run the script.
- **Caregiver Lessons chip state** uses a NEW backend field:
  `has_pending_attempt` on each row of
  `GET /api/lessons/caregiver/{id}`.response.remaining[]. True when any
  attempt is in `{ready_to_sign, needs_practice}`. Chip reads
  "awaiting sign-off" (warn tone) in that case, "to do" otherwise.
- **`sonner` was removed** in Batch 3 due to a yarn/CRA resolve conflict.
  Native lightweight toast provider at `frontend/src/shell/Toasts.js`.
  Don't `yarn add sonner` back — port into the native provider if a new
  variant is needed.

## H. HUMAN_REQUIRED items still open

The automated tester cannot verify these — they need an on-device or
human-eye check:

1. **Jovelyn's seeded MP4 attempt plays** in `/signoff/<her_attempt_id>`
   (Batch-1 fix swapped WAV → MP4; need a human eye on the player).
2. **Chat quiz `1./2./3.` digits** render inside a real Spanish lesson
   walk at `/c/SNMT3Y` (visual confirmation that number prefixes are
   the digits and not localisation collisions).
3. **Rear camera opens** on an actual phone when the chat invokes the
   video capture. DOM `capture="environment"` is set; device behaviour
   is phone/OS dependent.
4. **403 toast surfaces visually** when a forged `X-Firstshift-Role`
   hits a gated endpoint (`ForbiddenToastBridge` wires it up; needs an
   eye to confirm the toast actually appears above the fold).
5. **Lowercase `/c/<code>` redirect uses `replace: true`** — hitting
   browser Back should land on the prior page, not on `/c/snmt3y`.
   Code is correct; needs manual click.
6. **Publish-with-1-quiz works through the UI button** — backend
   validator is confirmed unconstrained in Batch 2; the UI path still
   needs a human click to confirm no residual client-side guard fires.

## I. Deferred scope (don't do these without an explicit new brief)

- **Ops features**: `Today` real logic (shift board), `Clients`
  staffing match, `New hires` voice intake, and swapping `build_plan`
  from mock to a real Gemini-wired pipeline.
- **Real auth** replacing `X-Firstshift-Role` + opening-the-door
  endpoints like `POST /api/grading/clips` and the caregiver chat.
- **Signed media tokens** instead of public UUIDs.
- **Professional translator pass** on `translations.es` + `.tl`
  content for seeded skills (current content is developer-written
  placeholders flagged in CHANGELOG).
- **WhatsApp / Twilio integration** — user explicitly dropped it.
  `conversations.channel` + `messages.channel` fields are preserved
  for forward-compat.
- **`backend/scripts/clean_test_residue.py`** — recommended at the end
  of each tester run, never written. Would delete tester-leftover
  question/lesson_job/upload rows + their GridFS blobs. Current cleanup
  has been manual.

## J. Test fixtures

### Caregivers (access codes regenerate on seed re-run)

| Name              | Agency              | Lang | Code     |
| ----------------- | ------------------- | ---- | -------- |
| Alex Johnson      | Sunrise Home Care   | en   | `2TBAFX` |
| Darius Williams   | Harbor Caregivers   | en   | `TRSR9T` |
| Jovelyn Santos    | Sunrise Home Care   | tl   | `7JT6DC` |
| Lucia Hernández   | Sunrise Home Care   | es   | `SNMT3Y` |
| María García      | Harbor Caregivers   | es   | `UHHGAB` |

If any code 404s, pull live values via `GET /api/caregivers/list`.

### Published skills

- **Glove removal** (hero skill, 7 steps, **check ids `g1..g7`**, full
  en content, placeholder es/tl).
- **Hand hygiene** (seeded, en + partial translations).
- **Blood pressure** (seeded).
- **Transfer** (at `version: 6` after Batch-4 bed-to-chair content
  pass; safety checks `c1`+`c3`+`c6`, technique checks `c2 c4 c5`,
  pre-v6 attempts still reference `c1..c5` only).

### Policies (developer placeholders — flagged for user revision)

- "Client refuses care"
- "Client falls"
- "Running late to a shift"

### Agency roles for the role-switcher

`Care Manager`, `Trainer`, `Scheduler`. Allow-sets pinned in
`docs/merge/mvp-hardening.md` Batch 3 and in CONTRACTS §11.

## K. Workflow pattern for the orchestrator

1. **Preflight.** Hit `GET /api/ai/health`. If 503, Gemini is down or
   the key is missing — fix before touching anything AI-dependent.
2. **Branch off `main` per feature**, not off `mvp-hardening`. Name
   the branch `<area>/<name>` (e.g. `ops/today`, `auth/real`).
3. **Each fork owns one `docs/merge/<name>.md`** with: scope, files
   added, shared-line changes (should be ≈none), new fields/endpoints,
   known limits, and manual test evidence.
4. **Zero shared-line changes expected.** If you need to touch
   `server.py`, `App.css`, or another feature's folder, list the change
   with a reason. Reviewers look for this first.
5. **Service stubs**: swap only your own stub (`backend/services/<name>_service.py`),
   leaving the others alone so other forks remain parallel-safe.
6. **Testing cadence**: use the testing agent at each phase/batch
   boundary — once per fork at completion, and after any batch of fixes
   inside a hardening pass. Do NOT testing-agent after every commit.
7. **Scope decisions** go through `ask_human` with 2-4 options, never
   implementation details.
8. **Finish-tool only after** the testing agent passes and
   `docs/merge/<fork>.md` is populated.

## L. Pointer list — read these next

- **`docs/CONTRACTS.md`** — endpoint shapes, collection fields, pinned
  API shapes (sections 1a/1b/1c for the critical ones).
- **`docs/CHANGELOG.md`** — chronological "what shipped when" entries,
  one paragraph per phase or fork.
- **`docs/merge/grading.md`** — Grading fork deep-dive: adaptive 3-run
  pipeline, ffmpeg transcode, stale sweeper, signoff validation order.
- **`docs/merge/lessons.md`** — Lessons fork deep-dive: chunked upload,
  job state machine, publish wipe, translation retry.
- **`docs/merge/channel-questions.md`** — Chat FSM, policy miss →
  inbox → card creation cycle, Gemini audio transcription, WhatsApp
  deferral record.
- **`docs/merge/mvp-hardening.md`** — ALL 4 batches with per-item
  rationale + the pinned endpoint × role matrix.
- **`memory/test_credentials.md`** — caregiver codes, Glove-removal
  skill id lookup, curl one-liner for a manual grading attempt.
