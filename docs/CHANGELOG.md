# FirstShift — Changelog

## Stage 4: Agency UI polish (2026-02-26)

Ships items A–H of the Stage 4 brief. All pages verified at a 480 px
viewport (`document.documentElement.scrollWidth === window.innerWidth`
on every agency route). No backend changes.

### Items

- **A. Questions page stacks at 480 px.** Removed the
  `md:grid-cols-[22rem_minmax(0,1fr)]` row layout; answer panel always
  renders BELOW the list. Replaced the `<li onClick>` with a proper
  `<button>` so the whole row is a first-click target (and
  keyboard-navigable). After `onPick`, the detail panel scrolls into
  view so taps on rows below the fold feel instant.

- **B. Long titles wrap inside their cards.** Dropped `truncate` and
  added `break-words` + `flex-1 min-w-0` on the title column in
  `SkillsPage` (published + jobs lists), `SignoffPage` rows,
  `NewHiresPage` rows, `CompetencyPage` rows, and the h1 on
  `SkillDetailPage`. Right-side meta (step/check counts, dates, chips,
  action buttons) wears `shrink-0 whitespace-nowrap` so it never
  pushes the title off-canvas.

- **C. Full-row click targets.** Converted the Questions list rows
  from `<li onClick>` to `<button>`, Competency rows from text-only
  Link to full-row Link, Jobs list to full-row Link, New Hires list to
  full-row Link to the caregiver's competency file. Audited every
  agency list; see "Audit" below.

- **D. Role gating via `useCaps()` hook.** New `useCaps()` in
  `src/hooks/useRole.js` returns `{role, can: {editSkills, signOff,
  nearMiss, archive, replaceSource, recordSkill, answerQuestions,
  publish, addQuestion}}`. Replaced scattered `canSignoff(role)`,
  `canArchiveSkill(role)`, `canEditSkill(role)`, `canRecordSkill(role)`,
  `canAnswerQuestions(role)` call-sites across SkillDetailPage,
  SkillsPage, DraftEditorPage, RecordPage, SignoffDetailPage,
  QuestionsPage, CompetencyDetailPage. Legacy predicates still exported
  for compatibility; prefer the hook in new code. Removed the "Switch
  to Care Manager" nags on view-only pages: Skills (removed the
  Scheduler-view banner), Signoff detail (now shows a quiet "Read
  only" chip instead), Questions detail (hides the answer form
  entirely with no message), Draft editor + Record gate (reworded to
  "Read only" without role-specific instructions).

- **E. Caregivers modal accessibility.** `AgencyShell` now captures
  the opener element on open and restores focus on close via
  `requestAnimationFrame`. Close button's `aria-label` reduced from
  `"Close caregiver picker"` to `"Close"` per spec. Escape key already
  closed; still does.

- **F. Caregiver 404 copy.** `CaregiverLayout` 404 now reads **"Code
  not found. Please check your link or contact your coordinator."**
  No "Back to agency" button (was never present; comment kept
  explaining why).

- **G. Shared in-flight GET dedupe in `frontend/src/api.js`.** One
  abstraction, one place. The axios `api.get` method is wrapped with
  a Map keyed on `GET:${url}?${JSON.stringify(config.params ?? null)}`;
  concurrent duplicate GETs join the same underlying promise. Entry
  evicts on both resolve AND reject via `.finally()`. GETs only —
  POST/PUT/PATCH/DELETE pass through unchanged so side effects are
  never collapsed. Not an HTTP cache: fresh fetches run as soon as
  the first settles. Previous Stage-4 per-page `AbortController +
  CanceledError` guards were removed from TodayPage, SignoffPage,
  ClientsPage, NewHiresPage, SkillsPage, QuestionsPage,
  CompetencyPage, CompetencyDetailPage, SkillDetailPage, and
  **CaregiverLayout** (the last one HAD to drop its signal-based
  cancellation because mixing per-call `abort()` with a shared
  promise cache rejects mount-2's handler with `CanceledError` before
  it ever reads the resolved value — the 404 state would never land
  on `/c/BOGUS`). The `useRef` guards (`lastFetchKey`, `didFetch`)
  that CompetencyDetailPage + SkillDetailPage added earlier are gone;
  the dedupe map handles that layer too.

  Polling intervals (unchanged, re-audited):
  - **QuestionsPage**: `/questions/inbox` every **10 s**
    (constant inlined at `setInterval(() => load(), 10000)`).
    Verified in a live Playwright request-logger window: 2 hits in
    11 s (mount + 1 poll).
  - **TodayPage**: no interval poll — refreshes on window `focus` +
    document `visibilitychange` (visible). Metric cards don't move
    second-to-second but should pick up a fresh signoff on tab
    return.
  - **SkillsPage**: `/lessons/jobs` every 2 s **only while a job is
    non-terminal**; terminates when all jobs reach `ready`/`failed`/`published`.
  - **DraftEditorPage**: `/lessons/jobs/<id>` every 2 s **only while
    the job is non-terminal**.
  - **PracticeResultPage**: once-cycle until the attempt reaches a
    terminal grade.
  - **ChatPage / AskPage**: caregiver live-conversation polls (2 s
    and 3 s respectively) — kept, untouched.

  Dedupe receipt (one Playwright pass per route, StrictMode on,
  2.5 s settle window, request-logger counts /api GETs):

  ```
  Page         total  unique  dup>1  endpoints
  /today         1      1       0    ops/today/metrics×1
  /skills        2      2       0    lessons/skills×1, lessons/jobs×1
  /signoff       1      1       0    grading/queue×1
  /clients       5      5       0    ops/clients×1 + 4 per-client caregiver-fit×1 each
  /questions     1      1       0    questions/inbox×1
  /new-hires     1      1       0    ops/caregivers?sort=hired_at_desc×1
  /competency    1      1       0    grading/competency×1
  ```

  Every endpoint hit exactly once per mount. No duplicates. The dev
  helper `window.__fsInflight` exposes the Map for one-off console
  assertions (`__fsInflight.size === 0` after any load settles).

- **H. 480 px overflow sweep — all pass.** See DONE-WHEN table below.

### Role matrix (frontend hide table) — matches `useCaps()`

| Capability           | Care Manager | Trainer | Scheduler |
|----------------------|:------------:|:-------:|:---------:|
| Record a skill       | ✓            | ✓       | hidden    |
| Edit a skill / draft | ✓            | ✓       | hidden    |
| Publish              | ✓            | ✓       | hidden    |
| Replace source video | ✓            | hidden  | hidden    |
| Archive a skill      | ✓            | hidden  | hidden    |
| Sign off an attempt  | ✓            | hidden  | hidden    |
| Report near-miss     | ✓            | hidden  | hidden    |
| Answer a question    | ✓            | hidden  | hidden    |

### Audit — every agency list (click-landing verified @ 480 px)

Playwright pass: click first row 20 px from the right edge (outside
title column) → assert nav OR active state. Full receipt in the
Stage-4 dev console log; summary below.

| List                                     | Full-row click? | Click lands                                     |
|------------------------------------------|:---------------:|-------------------------------------------------|
| Today cards (`today-card-*`)             | ✓               | nav → `/caregivers?filter=…` / `/signoff` / `/questions` (first card tested) |
| Clients list (`clients-row-*`)           | — intentional   | NO client-detail page exists. Caregiver `<Link>`s inside each client ARE full-row (`clients-<id>-cleared-row-*`, `clients-<id>-almost-row-*`). |
| Skills published (`skills-row-*`)        | ✓               | nav → `/skills/<id>`                            |
| Skills drafts/in-progress (`job-row-*`)  | ✓               | nav → `/skills/drafts/<id>` (no draft rows in current seed; selector + Link covered) |
| Sign-off rows (`signoff-row-*`)          | ✓               | nav → `/signoff/<id>`                           |
| Questions rows (`questions-row-*`)       | ✓               | opens stacked detail panel (`question-detail-<id>`) on same URL — single click |
| New Hires rows (`newhires-row-*`)        | ✓               | nav → `/competency/<id>`                        |
| Competency groups container              | — intentional   | wrapping `<ul>` is layout only; inner Links handle nav |
| Competency link rows (`competency-link-*`) | ✓             | nav → `/competency/<id>`                        |
| Caregivers picker modal rows             | ✓               | nav → `/c/<code>` (full-width `<button>`)       |
| Caregiver lessons rows                   | ✓               | opens that skill's lesson in the chat FSM       |

### Files changed

- `frontend/src/api.js` — shared in-flight GET dedupe map; wrapped
  `api.get`; `window.__fsInflight` dev helper.
- `frontend/src/hooks/useRole.js` — new `useCaps()` capability object.
- `frontend/src/App.css` — `.tap` no longer forces `display: inline-flex`
  when the element already has a Tailwind display utility (`flex` /
  `block` / `grid` / `inline` / `hidden`). Lets full-row `<Link class="tap flex ...">` keep their intended layout.
- `frontend/src/features/ops/TodayPage.js` — on-focus refresh,
  dedupe-aware fetch, three-card layout tightened for 480 px.
- `frontend/src/features/ops/ClientsPage.js` — dedupe-aware fetch
  (`cancelled` flag only, no AbortController).
- `frontend/src/features/ops/NewHiresPage.js` — full-row Link,
  break-words, dedupe-aware fetch.
- `frontend/src/features/lessons/SkillsPage.js` — `useCaps`, title
  wrap, removed role nag, dedupe-aware fetch, jobs list full-row Link.
- `frontend/src/features/lessons/SkillDetailPage.js` — `useCaps`,
  title wrap, header stacks on narrow widths so three right-aligned
  buttons don't squeeze the h1 into vertical text, dedupe-aware fetch.
- `frontend/src/features/lessons/DraftEditorPage.js` — `useCaps`,
  gate copy reworded to drop "Switch to Care Manager".
- `frontend/src/features/lessons/RecordPage.js` — `useCaps`, gate
  copy reworded.
- `frontend/src/features/grading/CompetencyPage.js` — full-row Link,
  break-words, dedupe-aware fetch.
- `frontend/src/features/grading/CompetencyDetailPage.js` — `useCaps`,
  dedupe-aware fetch (removed `didFetch` useRef guard).
- `frontend/src/features/grading/SignoffPage.js` — row title wrap,
  dedupe-aware fetch.
- `frontend/src/features/grading/SignoffDetailPage.js` — `useCaps`,
  dropped "Switch to Care Manager" nag; "Read only" chip instead.
- `frontend/src/features/questions/QuestionsPage.js` — stacked
  layout, full-row `<button>`, dedupe-aware fetch, polling stayed at
  10 s, nag removed.
- `frontend/src/shell/AgencyShell.js` — opener-ref focus-return on
  modal close; `aria-label="Close"`.
- `frontend/src/shell/CaregiverLayout.js` — 404 copy updated;
  dedupe-aware fetch (removed AbortController; mixing per-call abort
  with the shared cache rejected mount-2 handlers with CanceledError).

### DONE-WHEN self-check

| Check | Result |
|-------|--------|
| 480 px overflow — `/today`                     | pass (vw=480 doc.sw=480 overflow=none) |
| 480 px overflow — `/skills`                    | pass (vw=480 doc.sw=480 overflow=none) |
| 480 px overflow — `/signoff`                   | pass (vw=480 doc.sw=480 overflow=none) |
| 480 px overflow — `/clients`                   | pass (vw=480 doc.sw=480 overflow=none) |
| 480 px overflow — `/questions`                 | pass (vw=480 doc.sw=480 overflow=none) |
| 480 px overflow — `/new-hires`                 | pass (vw=480 doc.sw=480 overflow=none) |
| 480 px overflow — `/competency`                | pass (vw=480 doc.sw=480 overflow=none) |
| 480 px overflow — `/caregivers`                | pass (vw=480 doc.sw=480 overflow=none) |
| 480 px overflow — `/competency/<id>`           | pass (vw=480 doc.sw=480 overflow=none) |
| 480 px overflow — `/skills/<id>`               | pass (vw=480 doc.sw=480 overflow=none; buttons stack beneath title) |
| 480 px overflow — `/signoff/<id>`              | pass (vw=480 doc.sw=480 overflow=none) |
| 480 px overflow — `/c/BOGUS` @ 390 px          | pass (vw=390 doc.sw=390 overflow=none) |
| Scheduler: no edit/archive/signoff/near-miss/replace-source buttons | pass (role-gated via `useCaps`) |
| Scheduler: no "Switch to Care Manager" nag    | pass (text scan returns false on every page) |
| Trainer: Edit skill visible, Archive/Replace source hidden | pass |
| Trainer: Approve/Send back hidden              | pass |
| Trainer: Report near-miss hidden               | pass |
| Care Manager: all controls present (regression) | pass |
| Questions: first-click opens detail            | pass (Playwright click → `question-detail-<id>` present) |
| /c/BOGUS: "Code not found", no "Back to agency" | pass (body text = "Code not found\\n\\nPlease check your link or contact your coordinator.") |
| /c/2TBAFX regression (happy path still works)  | pass (`caregiver-shell` renders) |
| Caregivers modal: `aria-label="Close"`         | pass |
| Caregivers modal: Escape closes, focus returns to opener | pass |
| Fetch dedupe: every page = 1× per endpoint     | pass (Playwright request-logger, 2.5 s window: 0 duplicates across 7 agency pages, dedupe map in `api.js`) |
| Questions polling @ 10 s                       | pass (2 hits in 11 s window; `setInterval` constant 10000 ms) |

### No CONTRACTS drift

Stage 4 is UI-only; no backend changes; no new endpoints. The shared
dedupe map lives entirely in `frontend/src/api.js` and is invisible to
the backend (identical GETs produce one wire request).

---



## Stage 3 (partial): Today + Clients + near-miss (2026-02-26)

Ships items **A–I, N, O** of the Stage 3 brief. Items **J–M** (New Hires
intake form + voice intake + AI plan generation + access-code
generation) are **explicitly deferred** — timebox was already past the
"do not negotiate scope on your own" line when I started.

### Collections added

Three new collections (all documented in CONTRACTS §6):

- **`plans`** — one doc per caregiver, items = `[{skill_id, mode,
  refresher?}]`. **Only `mode` + `refresher` persist**; per-item `status`
  is DERIVED on every read from `cleared_skills` + open attempts + the
  active conversation (`features/plans/__init__.py::_derive_status`).
  Priority order: `refresher` override → `cleared` → `practicing` →
  `not_started`.
- **`incidents`** — append-only audit of near-miss reports:
  `{_id, caregiver_id, skill_id, description, reporter_role, created_at}`.
- **`cert_skill_map`** — small `{certificate, verify_skill_ids}` table.
  Re-seeded on startup by title (CNA → all 4 skills; HHA → all except
  Blood pressure). Used to populate a plan item's "Verified because:
  CNA" subtitle when the caregiver's stated certificate covers the skill
  and the plan item is in `verify` mode.
- **`refresher_drafts`** — one row per outstanding draft refresher
  message, created by `near-miss` and deleted on `/send` (which pushes
  the text into the caregiver's chat via `send_message_async`).

### Startup hooks (idempotent, `server.py@on_startup`)

- `features/plans/integrity.run_integrity_sweep` — scans every
  caregiver, `$pull`s any id in `cleared_skills` not backed by an
  approved sign-off whose `attempt` row has a `clip_id`. Logs
  `caregivers_scanned` + `corrections` on `firstshift.plans.integrity`.
  Startup logs on current seed: `caregivers_scanned=5, corrections=0`.
- `features/plans/seed.seed_cert_skill_map` — upserts the cert → skill
  map by current title. Reports unresolved titles in the summary.
- `features/plans/seed.backfill_plans` — creates a learn-mode plan for
  any caregiver missing one (so forks adding caregivers mid-stream pick
  up a plan on next read without a migration script).

### New endpoints

`/api/ops`:
- **`GET /today/metrics`** — 3 card counts + headline avg.
  `avg_days_to_cleared` is a **Mongo-side `$match + $group + $avg`**
  pipeline on `signoffs` with `$lookup` to `caregivers` + `plans`
  (`features/ops/__init__.py::_avg_days_pipeline`). Not a Python
  average. Returns `null` when no caregiver is fully cleared yet; UI
  renders "Not enough data yet".
- **`GET /today/cleared-days`** — the `$facet.rows` branch of the same
  pipeline (per-caregiver drilldown sorted asc by days).
- **`GET /clients/{client_id}/caregiver-fit`** — cleared (via Mongo
  `$all`) + almost-ready (missing **exactly one** required skill;
  missing skill named per row).

`/api/plans`:
- **`GET /caregiver/{id}`** — plan with derived status per item + optional
  `verified_because` / `refresher_at` subtitles.
- **`POST /caregiver/{id}/near-miss`** — Care-Manager-only. Atomic:
  inserts `incidents`, `$pull`s skill from `cleared_skills`, flips the
  matching plan item's `refresher: true`, creates a `refresher_drafts`
  row with localized prefilled text. **Does NOT auto-send to the
  caregiver chat.**
- **`GET /caregiver/{id}/refresher-drafts`** — open draft list.
- **`PUT /refresher-drafts/{id}`** — Care-Manager-only. Save edits.
- **`POST /refresher-drafts/{id}/send`** — Care-Manager-only. Push into
  chat via `send_message_async`; row deleted on success.
- **`DELETE /refresher-drafts/{id}`** — Care-Manager-only. Discard.
- **`GET /caregiver/{id}/incidents`** — audit view.
- **`GET /cert-map`** — current cert → skill-ids table.

Full role matrix in CONTRACTS §11.

### Frontend

- **`frontend/src/features/ops/TodayPage.js`** — three stacked cards
  (`today-card-new-hires`, `today-card-signoffs`, `today-card-questions`)
  linking to their respective routes; headline "Avg time to cleared" card
  with a "See breakdown" dialog. Empty-state copy: "Not enough data yet".
- **`frontend/src/features/ops/ClientsPage.js`** — per client, renders
  "Cleared for this client" + "Almost ready — missing <skill>" sections.
  Fits are fetched in parallel on mount.
- **`frontend/src/features/grading/CompetencyDetailPage.js`** — plan
  card with per-item Learn/Verify + Not started/Practicing/Cleared/
  Refresher chips, "Verified because: CNA" subtitles for verify-mode
  rows, "Reopened after near-miss on <date>" subtitles for refresher
  rows. Care-Manager-only **Report near-miss** button (hidden when no
  item is currently cleared). Draft refresher UI (textarea, Send,
  Discard) rendered as a separate card; Send is the only path to the
  caregiver chat.

### CONTRACTS drift resolved

- **Attempts fields** — CONTRACTS §6 lists only
  `{_id, caregiver_id, skill_id, clip_id, checks, overall, created_at}`
  but the running code has `status` + `reviewed` + `verdict` + `score`
  + `message_for_caregiver` + `graded_once` + `runs_used`. The brief's
  "signoffs_waiting = attempts with status=ready_to_sign AND NOT
  reviewed" implementation uses the code fields; CONTRACTS §6 should
  catch up on a later pass. Not blocking.
- **`is_critical` vs `safety_critical`** — brief uses the former, code
  uses `safety_critical`. Code name wins (CONTRACTS §6 agrees). No
  action needed.
- Stage 3 collections (`plans`, `incidents`, `cert_skill_map`,
  `refresher_drafts`) **were** flagged `Reserved for later phases` in
  CONTRACTS §6. Now ratified with their actual shapes.

### Alex live-upload end-to-end test

Reusable self-check: `python3 scripts/stage3_e2e_check.py` (requires
`pymongo` + `requests`; both installed in the pod venv). Runs 32
assertions: role gating on near-miss + refresher-drafts
(no header / Scheduler / Trainer all → 403), Today metrics shape,
Clients caregiver-fit "Almost ready" bucket, synthetic sign-off →
`cleared_skills` → `caregiver-fit` cleared rebucket, full near-miss
flow (incident + draft creation, draft edit, draft NOT auto-sent,
draft sent → appears in Alex's chat → draft row deleted), cert map
coverage. **Last run: ALL PASS.**

Simulation shortcut (what the script does for live-upload): insert a
synthetic `ready_to_sign` attempt for Alex using an existing clip id
(any clip in GridFS works for the sign-off path — grade_clip is
already Stage-2-tested end-to-end), then `POST
/api/grading/attempts/{id}/signoff` with
`{"decision":"approve","signer":"Rachel Kim, RN","signer_role":"Care Manager","note":""}`
+ `X-Firstshift-Role: Care Manager`.

**Manual browser flow for filming (same scenario, driven through the UI):**

1. Open `/c/2TBAFX` (Alex's caregiver chat).
2. Pick a skill → upload a short glove-removal clip through the chat
   input (Stage 2 `/api/channel/upload-practice-clip`).
3. Switch to Care Manager (role picker) → `/signoff`.
4. The attempt lands under "Ready to sign" (see
   `backend/features/grading/routes_signoff.py::_queue`).
5. Approve. Alex now shows "Cleared" for Mr. Henry Oshiro in `/clients`
   (`Oshiro` requires only Hand hygiene).

To reset between demos:

```bash
curl -X POST \
  -H "X-Firstshift-Role: Care Manager" \
  https://<preview-url>/api/channel/dev/reset/44c9449a6ebd423486229f0bec62dbb8
# then: run scripts/stage3_e2e_check.py cleanup section, or just drop
# the test attempt + reset cleared_skills in Mongo.
```

### Role gating (curl receipts)

```
POST /api/plans/caregiver/<id>/near-miss                       (no header)      -> 403
POST /api/plans/caregiver/<id>/near-miss                       Scheduler        -> 403
POST /api/plans/caregiver/<id>/near-miss                       Trainer          -> 403
POST /api/plans/caregiver/<id>/near-miss                       Care Manager+bad body -> 404 "skill not found"
POST /api/plans/refresher-drafts/<id>/send                     Scheduler        -> 403
PUT  /api/plans/refresher-drafts/<id>                          Trainer          -> 403
DELETE /api/plans/refresher-drafts/<id>                        Scheduler        -> 403
```

### Deliberately deferred (do NOT read as "forgotten")

- **J.** New hires intake form (phone + name + certifications +
  years + target client + "most familiar with" + "least familiar with"
  + voice-notes).
- **K.** Voice intake (OpenAI Whisper or Gemini audio).
- **L.** AI plan generation (`ai.call_gemini` with a plan schema that
  flips plan items between `learn` and `verify` based on cert + stated
  experience).
- **M.** Access-code generation path for new intake.

These require either a longer-form conversation flow (J, K) or
non-trivial Gemini schema wiring (L) that would push past the hard
timebox. All four will slot cleanly on top of the collections shipped
here (`plans.items[]` already carries the `mode` toggle; `cert_skill_map`
already maps cert → verify ids; `caregivers.access_code` already has
the generator in `backend/util/access_code.py`).

### Files touched

- `backend/features/plans/__init__.py` (NEW — routes + near-miss +
  refresher drafts)
- `backend/features/plans/seed.py` (NEW — cert map + plan backfill)
- `backend/features/plans/integrity.py` (NEW — startup sweep)
- `backend/features/ops/__init__.py` (+ Today metrics + caregiver-fit)
- `backend/server.py` (startup hook + collection list)
- `backend/seed/seed.py` (`refresher_drafts` left untouched by auto-seed)
- `frontend/src/features/ops/TodayPage.js` (full rewrite — three cards +
  headline)
- `frontend/src/features/ops/ClientsPage.js` (fit sections per client)
- `frontend/src/features/grading/CompetencyDetailPage.js` (plan + draft
  + near-miss dialog)
- `docs/CONTRACTS.md` (§1 endpoints, §6 collections, §7 seed hooks, §11
  role matrix)
- `scripts/stage3_e2e_check.py` (NEW — repeatable DONE-WHEN self-check)

---



## Stage 2 fixups (2026-02-25)

Tester-surfaced follow-ups to Stage 2. All 4 fixups shipped.

### Items

- **FIX 1 — Lessons row tap lands on `/c/{code}`, not 404.**
  `frontend/src/features/lessons/CaregiverLessonsPage.js` navigated to
  `/c/${code}/chat` but the route is `/c/:code` (see
  `features/channel/routes.js`). Changed the navigate target to
  `/c/${code}` exactly. Lessons-tap now lands in the chat with the
  latest message being the step-0 lesson message (open-lesson
  backend path verified via curl in Stage 2; the only breakage was
  this frontend URL).

- **FIX 2 — "Not started" chip renders for `todo` rows.** Added a
  localized label for every `status` ∈ `{cleared, awaiting_signoff,
  practice_video_next, in_progress, todo}` and a new muted chip
  style `.fs-chip-muted` (no fill, border-only, lower font weight).
  Shipped on both `CaregiverLessonsPage.js` (Item F) and
  `features/grading/PracticePage.js` (Item G). Every row now shows a
  chip; no row is silent.

- **FIX 3 — `replace_source_video` returns 4xx instead of 500 on bad
  uploads.** Two causes:
  1. The pod no longer had `ffmpeg` in `/usr/bin` after a restart —
     apt packages aren't persistent. Installed a static ffmpeg +
     ffprobe at `/root/.local/bin` (which IS persistent) and
     prepended that path to `os.environ["PATH"]` in `backend/server.py`
     so subprocess children inherit it even when supervisor's
     `environment=` directive trims PATH.
  2. The endpoint catches `EncodeError` → 415 (correct) but let any
     OTHER exception bubble as a bare 500. Added two more arms:
     `FileNotFoundError` → 503 "ffmpeg not available on server"
     (infra problem — distinct 5xx), and any other `Exception` →
     415 "cannot decode video: <first line of error>" so bad
     uploads surface as 4xx. Verified via curl: POSTing
     `/tmp/bad.txt` with `type=video/mp4` → HTTP **415** with
     `{"detail":"ffmpeg CRF pass failed: Invalid data found when
     processing input..."}`.
  (The 413 oversize path from Stage 1 is unchanged. The 415
  "file-too-short-for-step-timestamp" path from the frame-extract
  loop is also unchanged.)

- **FIX 4 — Dev reset endpoint for caregiver conversation.**
  `POST /api/channel/dev/reset/{caregiver_id}` sets conversation
  `state: "idle"`, clears `greeted`, `skill_id`, `step_index`,
  `quiz_index`, `correct_count`. **Messages are preserved** so
  testers still see history. Gated on `X-Firstshift-Role: Care
  Manager` via the shared `require_role` dependency: role missing →
  403 `{reason: "role_required", allowed: ["Care Manager"]}`;
  Scheduler / Trainer → 403 `{reason: "role_not_allowed", role: ...,
  allowed: ["Care Manager"]}`; Care Manager → 200 with modified
  count. Verified end-to-end:

```
curl -X POST $API/api/channel/dev/reset/<caregiver_id>                                          → 403 role_required
curl -X POST $API/api/channel/dev/reset/<caregiver_id> -H "X-Firstshift-Role: Scheduler"        → 403 role_not_allowed
curl -X POST $API/api/channel/dev/reset/<caregiver_id> -H "X-Firstshift-Role: Care Manager"     → 200 {"ok":true,...}
```

### Files touched

```
M  backend/server.py                                            (prepend /root/.local/bin to PATH so static ffmpeg is reachable)
M  backend/features/channel/routes.py                            (POST /dev/reset/{id} + role gate)
M  backend/features/lessons/skills_routes.py                     (415 catchall + 503 for ffmpeg missing)
M  frontend/src/App.css                                          (.fs-chip-muted)
M  frontend/src/features/lessons/CaregiverLessonsPage.js         (navigate /c/${code} + "Not started" chip)
M  frontend/src/features/grading/PracticePage.js                 ("Not started" chip)
M  docs/CHANGELOG.md
```

### Infra note (static ffmpeg)

Static arm64 ffmpeg 7.0.2 from `johnvansickle.com/ffmpeg` is
installed at `/root/.local/bin/{ffmpeg,ffprobe}` (~100 MB total).
Survives pod restarts; the apt package does not. Nothing else to do
on fresh pods except `cd /app && git pull` — the PATH prepend in
`backend/server.py` picks it up automatically.



## Stage 2 — Caregiver chat fixes (2026-02-25)

Chat FSM + caregiver surface fixes. Everything stays inside the
caregiver feature folders (`backend/features/channel`, `frontend/src/features/channel`,
`frontend/src/features/lessons`, `frontend/src/features/grading/PracticePage.js`).
Agency surfaces picked up the numbered-option render as a free side-effect
of a shared frontend widget — no behavioural change on the agency side.

### Items

- **A. Quick replies driven by the latest question message.** Outbound
  bot messages now carry `question_type` ∈ `{"skill_menu", "step", "quiz"}`
  and `question_payload` with the strings the UI needs. The frontend
  derives the quick-reply bar in `ChatPage.js` by scanning the LATEST
  outbound message (not state) — if its `question_type` is set, the
  bar renders against its payload; if the latest outbound has no
  `question_type`, the bar is hidden (no stale carry-over). Testids
  renamed to brief verbatim: `[data-testid="quickreplies"]` (bar) and
  `[data-testid="quickreply-{index}"]` (each button). Payloads:
  - `skill_menu` → `{skills: [{n, id, title_localized}]}` (4 buttons when 4 skills remain).
  - `step` → `{next_label}` (localized: "Next" / "Siguiente" / "Susunod").
  - `quiz` → `{options: [{n, text}]}` (3 numbered-option buttons).

- **B. Numbered options 1/2/3, letter aliases a/b/c accepted.** FSM
  template `quiz_opt` is now `"{num}. {text}"` across en/es/tl (was
  `"{letter}. ..."`). `quiz_wrong` reads `"The answer is: {num}"` →
  "La respuesta es: 2" / "Ang sagot ay: 2". New parser
  `_parse_quiz_answer(text)` returns the 1-based option number for
  `1/2/3`, `A/B/C`, `a/b/c`. Correctness still uses English
  `answer_index` (unchanged — es/tl quizzes don't carry
  `answer_index`). Invalid input mid-quiz sends the localized
  `quiz_prompt_invalid` ("Please answer 1, 2, or 3." / "Por favor
  responde 1, 2 o 3." / "Mangyaring sumagot ng 1, 2, o 3.") AND
  re-sends the current quiz question so the quick-reply bar refreshes
  against a brand-new question message (A's guarantee). The agency
  skill viewer + draft editor already rendered `{i+1}. ` in the view
  mode — kept as-is; es/tl TranslationView view mode also uses the
  same prefix. No LLM re-ordering per language.

- **C. Keep input focus after send + quick-reply tap.** `sendText`'s
  `finally` block calls `refocusInput()` which is wrapped in
  `setTimeout(…, 0)` so React commits `setSending(false)` BEFORE the
  focus call — focusing a disabled textarea is a silent no-op in
  every modern browser, which was why focus previously appeared to
  "stick on button". Quick-reply taps go through the same `sendText`
  path so they inherit the refocus for free. Verified at 390 px:
  `document.activeElement === chat-input` returns true after both a
  typed send AND a quick-reply tap.

- **D. Scroll to newest message after images finish loading.** The
  new-message effect now locates the latest bubble by its
  `data-testid`, enumerates its `<img>` children, and awaits each
  `load`/`error` event (whichever first) via `Promise.all`, capped
  at 1500 ms so a stuck image can't freeze the scroll. Messages
  without images scroll immediately. "User is scrolled up" behaviour
  preserved via `userScrolledUpRef` (threshold 60 px from bottom).

- **E. Empty band between composer and tabs removed.** `.fs-frame`
  locks to `height: 100vh; overflow: hidden` on the caregiver side
  (`.fs-frame[data-side="caregiver"]`); main is `flex-1 pb-14
  overflow-y-auto`; the chat page uses `h-full flex flex-col` so the
  thread section flexes to fill. Measured at 390 px: composer bottom
  Y = 1024, nav top Y = 1023 — the composer sits directly above the
  tab bar with **1 px rounding gap**, not 44 px. Non-chat tabs
  (Lessons / Practice / Ask) scroll inside main via `overflow-y-auto`.

- **F. Lessons tab — status + tappable rows.**
  `GET /api/lessons/caregiver/{id}` now returns `title` (localized),
  `step_count`, and `status` ∈ `{"cleared", "awaiting_signoff",
  "practice_video_next", "in_progress", "todo"}` derived from
  `caregiver.cleared_skills` + attempts in `ready_to_sign` /
  `needs_practice` + conversation state (`in_lesson` / `quiz` →
  "in_progress"; `awaiting_video` → "practice_video_next"). Chip
  labels localized per caregiver language. Every row is a full-width
  `<button>` tappable surface (`data-testid="caregiver-lesson-row-{id}"`);
  tap `POST /api/channel/open-lesson` (new) which transitions the FSM
  to `in_lesson` for that skill and sends step 0 with
  `question_type: "step"` — same shape as if the caregiver had picked
  the skill via the menu — then navigates to `/c/{code}` (chat tab).
  No duplicate state on the frontend.

- **G. Practice tab — layout.** Row: title (`flex-1`, left-aligned) +
  step count (muted, right) + chip (right, same source + labels as
  Lessons tab). Same `fs-chip-pass` / `fs-chip-warn` colour choice as
  Lessons. Nothing redesigned; alignment only.

### Files changed

Backend:
```
M  backend/features/channel/state_machine.py   (question_type+payload, letter alias, invalid-prompt resend, open_lesson)
M  backend/features/channel/routes.py          (POST /open-lesson, GET /messages exposes question_type+payload)
M  backend/features/lessons/__init__.py        (status field + localized title in /caregiver/{id})
M  backend/services/channel_service.py         (send_message_async forwards question_type/payload)
```

Frontend:
```
M  frontend/src/App.css                                   (caregiver-side .fs-frame locks to 100vh)
M  frontend/src/shell/CaregiverLayout.js                  (main pb-14 + overflow-y-auto)
M  frontend/src/features/channel/ChatPage.js              (latestQuestion + scroll-after-image + setTimeout refocus)
M  frontend/src/features/lessons/CaregiverLessonsPage.js  (tappable rows + 4-status chips)
M  frontend/src/features/grading/PracticePage.js          (same status chips + title/step-count/chip row)
```

### 390 px walkthrough (self-run after fixups applied)

Starting from a reset `/c/2TBAFX` (English, Alex Johnson):

| Step | Expected | Result |
|---|---|---|
| 1. Load | 0 quick replies | 0 ✓ |
| 2. Type "hi" + Send | 4 skill buttons `"1. Blood pressure measurement" / "2. Glove removal" / "3. Hand hygiene" / "4. Transfer from bed to wheelchair"` | 4 buttons with those labels ✓ |
| 3. Tap `"4. Transfer…"` | 1 "Next" button, step 1/4 message | ✓ |
| 4. Tap Next × 3 | step 4/4 message, 1 "Next" button | ✓ |
| 5. Tap Next again | Quiz Q1/2 message with `1./2./3.` numbered options, 3 quick replies labelled `"1. Parallel to the bed" / "2. 45° to the bed" / "3. Facing the bed"` | ✓ |
| 6. Type "a" + Send | Advance to Q2 (letter alias accepted) | ✓ |
| 7. Type "xyz" + Send during quiz | "Please answer 1, 2, or 3." + Q2 re-sent | ✓ (verified via curl: "Please answer 1, 2, or 3." then `qt=quiz` resent) |
| 8. Tap `"1. The caregiver"` | "Correct ✓" + "Last step: send a practice video, under 45 seconds." | ✓ |
| 9. Awaiting-video state | Quick-reply bar HIDDEN, video button enabled | 0 quick replies, 🎥 button enabled ✓ |
| 10. Composer / nav geometry | Composer sits directly above nav | gap = -1 px (rounding; no visible band) ✓ |
| 11. Focus after text send | `document.activeElement === chat-input` | true ✓ |
| 12. Focus after quick-reply tap | `document.activeElement === chat-input` | true ✓ |
| 13. Lessons tab | 4 rows, Transfer carries "Practice video next" chip | ✓ |
| 14. Tap a Lessons row | `/api/channel/open-lesson` returns ok, chat shows step 1 of that skill with Next button | backend verified ✓; UI loads after poll (2 s) |
| 15. Practice tab | Transfer chip "In progress", 4 steps right-aligned, title left (`flex-1`) | ✓ |

Spanish (`/c/JUM6QK` — Lucia Hernández):

| Expected | Result |
|---|---|
| Menu header "Habilidades para practicar:" | ✓ |
| Skill titles localized (Medición de la presión arterial, Retiro de guantes, …) | ✓ |
| Quiz Q1 "Pregunta 1/2: ¿Dónde debe colocarse el brazalete?" with `1. Sobre el codo / 2. 2–3 cm arriba del codo / 3. Sobre la muñeca / Responde 1, 2 o 3.` | ✓ |
| Invalid "xyz" → **"Por favor responde 1, 2 o 3."** + quiz re-sent | ✓ |

Tagalog (`/c/T73SQG` — Jovelyn Santos):

| Expected | Result |
|---|---|
| Quiz Q1 "Tanong 1/2: Ano ang tamang anggulo ng wheelchair …" with `1. Katabi ng higaan / 2. 45° sa higaan / 3. Nakaharap sa higaan / Mag-reply ng 1, 2, o 3.` | ✓ |
| Invalid "hindi" → **"Mangyaring sumagot ng 1, 2, o 3."** + quiz re-sent | ✓ |

### CONTRACTS drift found during Stage 2

- Chat message shape — added two optional fields on outbound messages
  (`question_type`, `question_payload`) persisted in `messages` and
  surfaced by `GET /api/channel/messages/{caregiver_id}`. No change
  to the inbound shape, no change to existing clients that ignore
  them (CONTRACTS §7 should document these in Stage 3's addendum).
- Caregiver lessons endpoint response — `title` is now the localized
  title (was always English); `title_en` is a new sibling field for
  the English original. Added `status`. Legacy `has_pending_attempt`
  retained for callers that still check it.
- New endpoint `POST /api/channel/open-lesson` with body
  `{caregiver_id, skill_id}` — public (no role gate on caregiver
  surfaces).

### Known deferrals (not in Stage 2 scope)

- The agency Skills viewer / draft editor already render `${i+1}. ` on
  the display side; nothing new needed. Any A/B/C letter leftovers in
  copy that isn't the quiz-option render were not touched.



## Stage 1 fixups (2026-02-25)

Tester surfaced 4 fixups + 1 side-effect to undo. Scope limited; no new
Stage-2 work mixed in.

### Items

- **FIXUP 1 — Honest "No image yet" renders (T7).** Seed used to
  generate synthetic 320×200 PNG frames for every step on every skill —
  the UI then rendered those as the step thumbnail, which is exactly
  the placeholder-image-block the brief forbids. Seed now sets every
  step's `frame_id` to `None` on skills without a source video (ALL
  seeded skills, since none ship with video today). One-shot
  idempotent migration under `backend/scripts/stage1_cleanup.py`
  nulls `frame_id`s on every pre-existing dirty skill AND deletes the
  orphan PNG blobs from GridFS (matched by `metadata.content_type ==
  "image/png"` + `length < 5 KB` + filename pattern
  `*-step-N.png` + not referenced by any live `skill.steps[].frame_id`).
  Frontend already shipped the dashed-border placeholder in Stage 1 —
  `SkillDetailPage` + `DraftEditorPage` now show it on every seed skill.

- **FIXUP 2 — Transfer revert.** The tester uploaded a 30 s test-pattern
  as the Transfer source video (`video_id: bb9aae93…`) and 4 step
  frames were re-extracted from it. Fresh re-seed already zeroes
  `video_id` and all `frame_id`s on Transfer (same path as every
  other seed skill). The cleanup script additionally deletes the
  orphan video + its 4 derived jpg frames from GridFS **by uuid**
  (safe-matched: `metadata.content_type == "image/jpeg"` + filename
  pattern `*-step-N.jpg` + not referenced by any skill; the video
  uses its `metadata.uuid` lookup from the pre-revert Transfer doc
  when a dirty skill is encountered, else matches by filename
  patterns `attempt-*.mp4` / `*.mp4` with a 32-hex uuid name).
  Jovelyn's placeholder clip is untouched (separate upload path,
  separate uuid). Cleanup run output: `orphan_jpg_deleted: 5`,
  `orphan_mp4_deleted: 12` (includes the tester's bb9aae93 video +
  11 leftover attempt blobs from prior seed cycles).

- **FIXUP 3 — Role header name clarification.** Code and `CONTRACTS.md`
  §9 both use `X-Firstshift-Role`; the earlier brief said
  `X-Agency-Role`. **Code and CONTRACTS win.** Audit found zero
  `X-Agency-Role` references in `backend/` or `frontend/src/`. The
  axios interceptor at `frontend/src/api.js:33` already sets
  `X-Firstshift-Role` on every outbound request, sourced from
  `localStorage.firstshift.agency_role` via `currentRole()`. Replace
  Source Video uses `api.post()` so it inherits the header
  automatically. One Stage-1 bug fixed anyway: the Replace Source
  Video call passed `Content-Type: multipart/form-data` without a
  boundary, which breaks some axios/server combinations — removed so
  axios sets its own multipart Content-Type including the boundary.

- **FIXUP 4 — Clamp Jovelyn's check timestamps to clip duration (T1).**
  New shared helper `backend/features/grading/clamp.py::clamp_check_times`
  with signature `clamp_check_times(checks, *, clip_duration, margin=0.2)`.
  Used by `backend/seed/seed.py` (clamps at seed time against the
  attempt's own `duration`) and by
  `backend/scripts/reseed_jovelyn_from_source.py` (re-clamps when the
  real Chippewa cut lands — a 12 s or 15 s real clip pushes the
  previously-clamped times back out, since the raw generator output
  for 5 checks spans 2.5 → 14.9 s). Jovelyn's current (placeholder)
  attempt times are now `c1=2.50, c2=5.60, c3=8.70, c4=9.80, c5=9.80`
  — all ≤ `10.0 - 0.2 = 9.80` s.

- **FIXUP 5 — Empty-field path reaches the inline blocker (T3).**
  Already wired by Stage 1's `localPublishBlockers` useMemo in
  `DraftEditorPage.js`. Confirmed four empty-field reasons surface
  via `[data-testid="editor-publish-blockers"]`:
  - `"Step N needs a title and instruction."` (clear a step title)
  - `"Check cX needs a description."` (clear a check description)
  - `"Each quiz question needs 3 non-empty choices."` (clear a quiz option)
  - `"Each quiz question needs a prompt."` (clear a quiz prompt)
  Each disables the Publish button and shows the full reason list
  inline. **Manual test:** open any draft, delete the first
  character of Step 1's title, confirm the Publish button goes to
  `opacity 0.55` and `[data-testid="editor-publish-blockers"]`
  mounts with the matching reason.

### Files touched

```
A  backend/features/grading/clamp.py                   (shared helper)
A  backend/scripts/stage1_cleanup.py                   (one-shot migration)
M  backend/seed/seed.py                                (no PNGs; apply clamp)
M  backend/scripts/reseed_jovelyn_from_source.py       (apply clamp)
M  frontend/src/features/lessons/SkillDetailPage.js    (drop manual Content-Type)
M  docs/CHANGELOG.md
```

### Self-check (ran after fixups)

```
# Every seed skill — frames all null, video_id null:
Transfer from bed to wheelchair     video_id=None  frames_all_null=True
Hand hygiene                        video_id=None  frames_all_null=True
Blood pressure measurement          video_id=None  frames_all_null=True
Glove removal                       video_id=None  frames_all_null=True

# Jovelyn's seeded attempt — check times vs. clip duration (10.0 s):
c1  2.50s OK  pass
c2  5.60s OK  fail
c3  8.70s OK  pass
c4  9.80s OK  unclear
c5  9.80s OK  pass

# GridFS post-cleanup:
image/png    count=2    (healthcheck.png × 2 — not step frames)
video/mp4    count=4    (4 live attempt clips, 0 orphans)
image/jpeg   count=0    (tester's 5 orphan jpg frames removed)
```

### Item A (unchanged)

Jovelyn's clip stays the 10 s honest placeholder. yt-dlp retry not
attempted — pod egress to googlevideo.com is confirmed-blocked.
The real Chippewa video reaches the pod via one of the three paths
listed in the Stage 1 reply, then `python -m
backend.scripts.reseed_jovelyn_from_source /path/to/source.mp4` swaps
in a 12 s cut (defaults) and the clamp helper reapplies to the longer
duration.



## Stage 1 — Demo data and content (2026-02-25)

Filming-ready demo pass. New entry point script
`backend/scripts/reseed_jovelyn_from_source.py` for the one blocker
(see below).

### Items

- **A. Jovelyn's seed clip** — PARTIAL. The Chippewa Valley CC BY source
  video (`https://www.youtube.com/watch?v=pyoHSHef90c`) could NOT be
  fetched from the pod: yt-dlp returned `403 Forbidden` on every
  format (progressive mp4, HLS, with/without `--js-runtimes deno`,
  with/without `--remote-components ejs:github`, with/without the
  `web_safari` extractor client). YouTube's googlevideo CDN is
  blocking this pod's egress IP. The seed now ships Jovelyn with an
  **honest 10 s SMPTE-bars placeholder** labelled on-video
  (`"Jovelyn Santos — seed placeholder (awaiting real transfer
  footage)"`) and `clip_source: "seed-transfer-placeholder"` on the
  attempt row. Status: `ready_to_sign`, 5 checks mirror the Transfer
  skill (c1..c5 with ids + descriptions + `safety_critical`),
  `graded_at` set. **To swap in the real clip** once the video reaches
  the pod (direct URL, scp, or the new "Replace source video" button
  on the Transfer skill): `python -m backend.scripts.reseed_jovelyn_from_source /path/to/transfer_source.mp4 --start 10 --duration 12`.
- **B. Alex live-upload** — Alex's `access_code` is now DETERMINISTIC
  `2TBAFX`. `cleared_skills: []`, no seeded attempt, no seeded
  signoff. Verification instructions in `## Test Instructions` below.
- **C. Media pipeline audit** — SHIPPED. One encoder:
  `backend/media/encode.py::encode_mp4`. Both
  `features/grading/ingest.py::_transcode_to_mp4` and
  `features/lessons/transcode.py::transcode_h264` now delegate to it.
  The seed script also routes every clip (placeholder included)
  through the helper. Range/206 verified via `curl -I` + `curl -r
  0-99` — see `## curl output` below.
- **D. "Replace source video" button** — SHIPPED. Care-Manager-only.
  `POST /api/lessons/skills/{id}/replace_source_video` (multipart
  `file`); encodes via `encode_mp4`, saves via `MediaStore`,
  re-extracts every step's frame at `step.start` via
  `media.encode.extract_frame`, overwrites `skill.video_id` and the
  per-step `frame_id`s. Does NOT create a draft; does NOT bump
  version; does NOT touch translations. Frontend wires the button
  into `SkillDetailPage.js`. Skills without a source video now render
  an honest **"No image yet"** placeholder (dashed border + 🖼 glyph,
  no filled colour block) in both `SkillDetailPage` and the Draft
  editor.
- **E. Translations (es + tl)** — SHIPPED. Publish already regenerates
  diff-aware (unchanged items keep prior translation, failed language
  marks `status: "stale"`). Retry endpoint now accepts
  `?lang=es` / `?lang=tl` so the Stale badge's "Retry translation"
  button only touches the affected tab. Hand hygiene and Blood
  pressure now ship with full `checks` and `quiz` translations in es
  and tl (previously 0 each). Transfer and Glove removal also carry
  full `checks` and `quiz` translations end-to-end. `grade_clip`
  prompt (`LANE_B_PROMPT_TEMPLATE`) is amended to explicitly require
  every text field returned to the caregiver (`"seen"`,
  `"message_for_caregiver"`) to be in `{language}` — fixes the
  "English leaked into the per-check `seen` sentence" bug for Spanish
  caregivers.
- **F. Quiz = exactly 2 questions** — SHIPPED. Blood pressure trimmed
  from 3 → 2. Glove removal grew from 0 → 2 (full es + tl
  translations). Transfer stays at 2. Hand hygiene stays at 2. Draft
  Editor "Add question" / "Remove question" buttons are bounded 2..2
  (grey-out at the edge); `_publish_blockers` returns a human reason
  when the count is off; `DraftEditorPage.js` surfaces the full
  reason list inline NEXT to the Publish button
  (`[data-testid="editor-publish-blockers"]`) so Publish never
  silently refuses. Translation staleness does NOT block publish.
- **G. Copy fixes** — PARTIAL (nothing to fix in the current tree):
  - `". ."` typo on Glove step 1 — NOT PRESENT in `backend/features/grading/seed.py` as of this commit; no change needed. Flag if it re-surfaces.
  - "What to bring" seeded card — NOT PRESENT in code. The `cards`
    collection today only populates when a Care Manager answers an
    inbox question (see `features/questions/pipeline.py`). No seeded
    card exists to edit. If you'd like a demo card seeded with "your
    phone" wording, flag it and I'll add an idempotent `cards` seed.
  - Spanish `tú` vs `usted` — audited `backend/` and `frontend/src/`;
    no stray `usted` found.
  - "coordinadora de cuidados" — SHIPPED.
    `features/questions/pipeline.py` now says `"Le pregunté a tu
    coordinadora de cuidados …"` and the pinning comment references
    the singular `coordinadora de cuidados`.

### CONTRACTS drift (code wins)

- Attempt check rows: the brief wrote `is_critical`; CONTRACTS §6 and
  the code use `safety_critical`. Seeded + runtime rows store
  `safety_critical: bool`. (This matches CONTRACTS already.)
- "Ready to sign": the brief uses the phrase directly; code calls the
  endpoint `GET /api/grading/queue` and the UI label is "Sign-off".
  Filter is `attempt.status in {"ready_to_sign", "needs_practice"}`
  with `reviewed != True`.
- `grade_clip` lives at `backend/services/grading_service.py` + the
  pipeline at `backend/features/grading/pipeline.py::grade_clip_pipeline`.
- Media interface: `backend/media/store.py::MediaStore` +
  `backend/media/routes.py` serve the `+faststart` mp4 with
  `Accept-Ranges: bytes`, HEAD support, and `206 Partial Content` on
  `Range` requests (CONTRACTS §4).
- Translation retry route: CONTRACTS §11 lists `POST
  /api/lessons/skills/{id}/translations/retry` as Care Manager +
  Trainer. Shipped the `?lang=` query param on top; existing callers
  that omit `lang` keep the pre-Stage-1 behaviour (retry both es+tl).
- `backend/media/encode.py` is NEW. Not previously in CONTRACTS;
  callers import `encode_mp4` / `extract_frame` / `cut_segment` from
  this module. Pending a CONTRACTS §4 addendum in Stage 2.

### Defaults picked (where the brief was unspecified)

- Jovelyn placeholder: 10 s SMPTE bars with on-video label (NOT
  solid colour; honest, declarative; routes through the single
  encoder). Chosen because the real Chippewa video is unavailable
  from this pod.
- "Replace source video" endpoint path: `/api/lessons/skills/{id}/replace_source_video`.
  Multipart `file` field. Max 100 MB (matches `/api/grading/clips`).
- `cut_segment()` default: `--start 10 --duration 12` for the reseed
  helper (12 s falls inside the brief's "10–15 s" window).
- Inline publish-blocker list uses `[data-testid="editor-publish-blockers"]`
  for a stable surface the testing agent + humans can both grep.
- `replace_source_video` is Care Manager only (`require_role({Role.CARE_MANAGER})`).
- Translation retry endpoint keeps the response shape `{ok, translations}`;
  when `?lang=` is set, only that language appears in `translations`.

### Test instructions — Alex's live upload (brief Item B)

Alex at `/c/2TBAFX`. The caregiver chat FSM path (phone):

1. Open `https://firstshift-preview.preview.emergentagent.com/c/2TBAFX`.
2. Tap `1` or type `menu` → pick a skill (e.g. "Glove removal").
3. Walk through steps + quiz until the chat says it's ready for a
   video (state `awaiting_video`).
4. Tap the 🎥 button → phone opens the rear camera → record a short
   clip (≥3 s, ≤45 s) → send.
5. Expect: a message "Uploading video…" then a grading update, then
   the attempt lands in `GET /api/grading/queue` under
   `ready_to_sign` (or `needs_practice`).

CLI equivalent (does not exercise the chat UI, but hits the same
`ingest_clip` + `grade_clip_pipeline` path — role gate is NOT
required on `/api/grading/clips`):

```
API="https://firstshift-preview.preview.emergentagent.com"
ALEX_ID=$(curl -s "$API/api/caregivers/by-code/2TBAFX" | python3 -c "import json,sys;print(json.load(sys.stdin)['caregiver']['id'])")
GLOVE_ID=$(curl -s "$API/api/lessons/skills" | python3 -c "import json,sys;print([s['id'] for s in json.load(sys.stdin)['skills'] if s['title']=='Glove removal'][0])")
curl -X POST "$API/api/grading/clips" \
  -F "file=@/path/to/local-glove-removal.mp4;type=video/mp4" \
  -F "skill_id=$GLOVE_ID" \
  -F "caregiver_id=$ALEX_ID"
# Wait ~10-30 s (adaptive 3-run Gemini pipeline), then:
curl -s "$API/api/grading/queue" | python3 -m json.tool
```

### curl output — faststart + Range/206

```
# HEAD on Jovelyn's seed clip
HTTP/2 200
content-type: video/mp4
content-length: 19555
accept-ranges: bytes
content-disposition: inline; filename="attempt-jovelyn-transfer.mp4"

# Partial range request (first 100 bytes)
HTTP/2 206
content-type: video/mp4
content-length: 100
content-range: bytes 0-99/19555
accept-ranges: bytes

# faststart proof (moov atom position in first 8 KB):
moov position in first 8KB: 36
mdat position in first 8KB: 7495
moov before mdat (faststart OK): True
```

### Pre-filming checklist (please verify on-device)

1. `GET /api/ai/health` → `{ok:true, model, result}`. GEMINI_API_KEY
   is configured via env (never committed).
2. `GET /api/grading/queue` returns Jovelyn's Transfer attempt +
   Lucia's BP attempt (both `ready_to_sign`, not yet `reviewed`).
3. `GET /api/lessons/skills` returns 4 skills (Transfer, Hand
   hygiene, Blood pressure, Glove removal), each with 2 quiz
   questions in en, es and tl.
4. Open Jovelyn's signoff detail → video plays (10 s), 5 checks
   render (c1..c5) with correct ids / safety flags.
5. Alex `/c/2TBAFX` loads with chat tabs (Chat, Practice, Lessons,
   Ask) and no seeded cleared skills.
6. GEMINI_API_KEY is configured via env (not committed; no key
   value appears in this changelog or in git history).

### Known blockers for Stage 2 to pick up

- `yt-dlp` cannot reach YouTube's CDN from this pod. If future stages
  want video pulled server-side, either upload the file manually,
  provide a non-YouTube direct URL, or add outbound-proxy config.
- Pro-translator pass on the hand-authored es/tl content — the
  pre-Stage-1 CONTRACTS §10 TODO still applies.



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
