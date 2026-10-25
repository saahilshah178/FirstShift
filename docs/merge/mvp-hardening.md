# Merge notes — `mvp-hardening`

> Branch: `mvp-hardening`, forked off `main` (post local-merge of `channel/questions`).
> Scope: MVP hardening — media, data integrity, grading reconciliation, role gating, UX polish.
> Ops/Today/Clients/New-hires deferred to a later fork.

## Hard decisions baked in

- **Duplicate skills**: hard-deleted the losers, migrated attempts/signoffs/cleared_skills/
  lesson_jobs/clients.required_skills refs to the winner (see **Dedup** below).
- **Quiz count**: no min/max — publish allowed with any `N` quiz questions, incl. 0.
- **Check-id prefixes**: the lane-B schema prefers `c1..cN`, but the validator now
  **preserves** any non-empty string id (editor path for seeded skills with legacy
  prefixes like `g1..g7` on Glove removal must not orphan attempt records). A
  non-standard id is logged as a non-blocking `"preserved"` problem, never renamed.
- **Draft API**: `PUT /api/lessons/jobs/{job_id}/draft` is a **full replace** of the
  draft (standard REST PUT, not a merge). The frontend editor sends the whole draft
  on every save; forks reusing this endpoint must do the same. See CONTRACTS §1c.
- **Role matrix** (shipped in Batch 3 — see full table in that section below):
  - **Care Manager** — unchanged, full access.
  - **Trainer** — no signoff, no question-answer, no card creation,
    no skill archive. Can record / edit skills + save translations.
  - **Scheduler** — view-only on skills (list + detail only); 403 on
    upload / edit / publish / archive / translation edit. Full access
    to Today / Clients / New-hires (ops endpoints still placeholders).
  - Backend is source of truth (`backend/roles.py`); frontend sends
    `X-Firstshift-Role` with every agency request and hides UI the
    role can't act on. A 403 pass-through surfaces a toast
    (`Your role doesn't allow this action. / Allowed: …`). **Real
    auth replaces this later — see CONTRACTS §10 TODO.**

## Files added (so far)

### Backend
- `backend/scripts/__init__.py`
- `backend/scripts/faststart_backfill.py`     — one-shot GridFS re-encode with `+faststart`.
- `backend/scripts/dedupe_skills.py`          — hard-delete loser skills + migrate refs.
- `backend/scripts/upgrade_glove_removal.py`  — Batch-1 #6 Glove content pass (frames, quiz, es/tl check translations).
- `backend/scripts/repair_cleared_skills.py`  — Batch-2 #7/#8 strip orphan clears + legacy status backfill.
- `backend/scripts/cleanup_orphan_drafts.py`  — Batch-2 #13 prune abandoned/duplicate `lesson_jobs` rows.
- `backend/scripts/backfill_seeded_timestamps.py` — Batch-2 tightening FIX B: distribute step timestamps across a skill's clip duration (ffprobe when a `video_id` resolves, 60s otherwise) when `steps[].start`/`end` are null.

(More files added per batch — kept in-sync below.)

### Docs
- `docs/merge/mvp-hardening.md` (this file).

## Shared-line changes

- `backend/media/routes.py` — rewritten `GET /{uuid}` to support HTTP byte-range (`Range:`
  → `206` with `Content-Range`, `Content-Length`, `Accept-Ranges: bytes`). Shape of
  `POST /api/media` and `GET /{uuid}` (full-body path) is byte-identical.
- `backend/media/store.py` — adds `open()` + `read_full(info)` + `read_range(info, start, end)`
  helpers; keeps `get()` for backwards-compat (returns the same tuple).

More per batch.

## Dedup winners / losers

Analysed by title and content richness. Rule: newest version with the most content wins
(frames, quiz, full translations).

| Family | Winner | Deleted losers |
| ------ | ------ | -------------- |
| Transfer / wheelchair | `c7691d94cef347f6bc03f3fc808939bd` — "Transferring a Patient from Bed to Wheelchair Using a Gait Belt", 5 steps + 5 checks + 2 quiz + full `es`/`tl` translations + reference video + extracted frames (v3 via `lessons/record`) | `f071e83edefe4d5aaecb68dc22dc35b1` (seed Transfer: 4 steps + 5 checks + 2 quiz, step-level translations only, PNG placeholders — not real frames)<br>`6184365a18544eb1a50294cc247a44d6` — "Transfer From Bed to Chair With a Gait Belt", 5 steps + 4 checks (less content than the winner) |
| Glove removal | `c60f1d3a9c44493b8c5e2fd5d3644d82` — "Glove removal", 7 steps + 7 checks (will be upgraded with frames + quiz + check translations by fix #6) | `6285be18f3e44afba30b649ce77ca8c0` — "Removing Gloves Technique", 5 steps + 6 checks |

Migration performed by `backend/scripts/dedupe_skills.py`:
- `attempts.skill_id` → winner.
- `signoffs.skill_id` → winner.
- `caregivers.cleared_skills` entry replaced with winner id (de-duped via `$addToSet` then `$pull`).
- `lesson_jobs.skill_id` → winner (so a draft that was linked to a loser Points at the winner).
- `clients.required_skills` entry replaced with winner id.
- `skills` row for each loser hard-deleted.

## DONE WHEN evidence

_Filled in per batch below once the fix lands and the smoke/tester has run._

### Batch 1 — media, data integrity

(evidence captured after batch complete)

### Batch 2 — signoff / competency / quiz / lazy edit

Tweaks folded in before the main fixes:

- **TWEAK-A (HEAD /api/media/{uuid})** — `backend/media/routes.py` grows a
  dedicated `@router.head("/{uuid_str}")` handler. iOS Safari / casting
  clients that probe size+content-type before `GET`+`Range` now see
  `200 OK` with `Content-Length`, `Content-Type`, `Accept-Ranges: bytes`
  and an empty body. Missing uuid still returns `404`. Verified via
  `curl -I`.

- **TWEAK-B (check-id prefixes)** — audited: Hand hygiene / Blood
  pressure / Transfer all use `c1..cN` (the schema contract in
  `features/lessons/schemas.py::validate_analyze`). **Glove removal uses
  `g1..g7`** (seeded manually in `seed/seed.py::_glove_skill`). One
  reviewed attempt row (`6853fc06…` / Lucia) references those `g*` ids;
  renaming would require rewriting that attempt's `checks[].id`. Per
  decision, **not renamed**. Future AI-authored skills continue to use
  `c*`; the Glove exception is documented here and intentional.

Fixes:

- **#7 / #8 — orphan clears stripped.**
  - `backend/scripts/repair_cleared_skills.py` — scans every caregiver,
    pulls any `cleared_skills` entry that lacks an approving signoff
    (accepts both `"approve"` and legacy seed value `"approved"`). For
    each stripped (caregiver, skill) pair, backfills a legacy attempt's
    `status`/`verdict` if the attempt had neither — using the same
    mapping as the live grader (`verdict pass → ready_to_sign`,
    `verdict retry → needs_practice`). Idempotent.
  - `features/grading/routes_signoff.py::_competency_for` — lazy guard:
    rebuilds `cleared` from the intersection of `cleared_skills` and
    approving signoffs; logs a warning on any residual orphan so the
    data drift is visible even without re-running the script.
  - Repair-run output (committed as evidence):
    - stripped `María García → Transfer`,
    - stripped `Jovelyn Santos → Hand hygiene`,
    - stripped `Jovelyn Santos → Transfer`,
    - backfilled attempt `68303aa8` → `needs_practice` ("hero" sign-off
      moment: Jovelyn now surfaces in the sign-off queue).

- **#9 — override / send-back note on competency detail.**
  - `frontend/src/features/grading/CompetencyDetailPage.js` — the row's
    `latest.note` renders as a `<blockquote>` directly under the
    "Signed by …" line, with warn-coloured left border when it was
    an `override` or `send_back`. Extra `space-y-3` between the signer
    line, the note block and the clip replaces the previous cramped
    `space-y-2`. `data-testid="competency-note-<skillId>"` added.

- **#10 — quiz count is free.**
  - `features/lessons/jobs.py::_publish_blockers` no longer requires
    `len(quiz) == 2`. Each present question still needs 3 choices and a
    valid `answer_index`; 0 questions is allowed.
  - `features/lessons/schemas.py` — `LANE_B_PROMPT` now asks Gemini for
    "a short set of 1 to 3 multiple-choice questions" and
    `validate_analyze` dropped the `len != 2` blocker.
  - `frontend/src/features/lessons/DraftEditorPage.js` — `+ Add
    question` header button, `Remove` button per quiz row, empty-state
    text when there are zero quiz items. New test-ids: `editor-add-quiz`,
    `editor-quiz-remove-<id>`, `editor-quiz-empty`.
  - Smoke test: edited Transfer skill from 2 → 1 quiz question, publish
    returned `{skill_id, version: N+1}` with Spanish+Tagalog translations
    carrying the single question through.

- **#11 — Spanish/Tagalog glove translations.**
  - Already landed in Batch 1 fix #6 (`upgrade_glove_removal.py`). Tester
    confirmed `es` and `tl` check arrays both have length 7. **No commit
    in Batch 2 for this item.**

- **#12 — quiz choices labelled `1./2./3.` everywhere.**
  - `frontend/src/features/lessons/SkillDetailPage.js` — the two
    `String.fromCharCode(65 + i)` sites (English view + translation
    read-only) now render `${i + 1}.`.
  - Draft editor already shows raw inputs; added a visible `1./2./3.`
    label next to each option so authors see the numeric labels they
    will see at playback time.

- **#13 — Edit skill is lazy; drafts don't accumulate.**
  - `features/lessons/skills_routes.py::open_edit_job` returns
    `{"job_id": f"edit-{skill_id}"}` and does NOT insert a `lesson_jobs`
    row. 404 still fires when the skill is missing.
  - `features/lessons/jobs.py` understands the `edit-{skill_id}` handle
    across `GET`, `PUT /draft`, `POST /steps/{n}/frame`, and `POST
    /publish`:
    - **GET** synthesises a draft view from the current published skill
      when there is no DB row (or when the only row is a terminal
      `published` breadcrumb from a prior session). This keeps the
      editor URL stable across publish → re-click → re-edit without
      "already published" dead-ends.
    - **PUT /draft** materialises the row on first save (requires
      `draft_rev: 0`) and refuses stale revs with `409` after that.
    - **POST /publish** rejects with `422 "No changes to publish — edit
      something first."` when the handle has no live row (user clicked
      Edit then hit Publish without touching anything).
    - **source_credit preservation**: on publish, if the editor's
      `source_credit` is empty, the existing skill's `source_credit`
      is kept rather than being silently cleared.
    - **post-publish wipe**: every `lesson_jobs` row for this
      `skill_id` is deleted after a successful publish. The published
      skill (`version` bump) is the audit trail; the drafts drawer
      stays clean.
  - `backend/scripts/cleanup_orphan_drafts.py` — one-shot: deletes
    `ready`/`failed` rows older than N minutes (default 60) that either
    have no `skill_id`, point at a skill that no longer exists, or are
    sibling-duplicates of the canonical `edit-{skill_id}` handle.
    Cleanup pass this batch: 4 orphans removed (2 abandoned new-skill
    drafts + 2 duplicate edit drafts for Blood pressure / Transfer).

- **#14 — chat video button opens the rear camera.**
  - `frontend/src/features/channel/ChatPage.js` — hidden file input's
    `capture="user"` → `capture="environment"`. One-liner. Mobile
    browsers that honour the attribute default to the rear-facing
    camera; desktop UAs ignore it (file picker still works).

## DONE WHEN evidence — Batch 2

```
# TWEAK-A
curl -I "$API/api/media/<vid>" → 200 w/ Content-Length, Accept-Ranges, Content-Type

# TWEAK-B (findings only; no code change)
Hand hygiene c1..c4 / Blood pressure c1..c5 / Transfer c1..c5 / Glove g1..g7 (intentional)

# #7 / #8
python -m backend.scripts.repair_cleared_skills
  → stripped 3 orphan clears; backfilled 1 legacy attempt
  → re-run → "nothing to strip" (idempotent)
curl $API/api/grading/queue
  → Jovelyn Santos / Transfer surfaces under `needs_practice`

# #10
PUT /jobs/edit-<skill>/draft with quiz=[q1 only]  → 200, draft_rev=1, quiz_count=1
POST /jobs/edit-<skill>/publish                   → 200, version N+1, es/tl have 1 quiz
POST /jobs/edit-<skill>/publish (no edits yet)    → 422 "No changes to publish…"

# #13
POST /skills/<id>/edit → {"job_id":"edit-<id>"}; no lesson_jobs row inserted
GET  /jobs/edit-<id>   → synthesised draft; draft_rev=0
PUT  /jobs/edit-<id>/draft → row materialises; draft_rev=1
POST /jobs/edit-<id>/publish → version N+1; row count for skill → 0
Click Edit again       → fresh synth; draft_rev=0

# #14
grep -n 'capture=' frontend/src/features/channel/ChatPage.js
  → capture="environment"
python -m backend.scripts.cleanup_orphan_drafts
  → deleted 4 orphan drafts (and nothing on re-run)
```

### Batch 2 — tightening pass (tester follow-ups)
Three required fixes + one cleanup folded into a single tightening commit:

- **FIX A — override chip spacing + capitalisation.**
  `frontend/src/features/grading/CompetencyDetailPage.js` — the override
  chip now lives inside a fragment with an explicit `{" "}` text node
  separating it from the `(role)` suffix, and the chip label is
  `"Override"` (title-case). Verified: `document.querySelector(...).
  textContent` on the signer line now reads
  `"Signed by Nurse Miller (Care Manager) Override"` with a real
  space, so copy-paste + screen readers no longer collapse the chip
  into the role name.

- **FIX B — seeded skills publishable after edit (option 2 chosen).**
  Decision: **backfill plausible timestamps**, not validator tolerance.
  Rationale: option 2 (even-distribution) *also* unlocks Batch-4 #21
  per-step reference-video playback, so the extra work has a second
  payoff; a `seeded: true` flag would require every reader to know
  about the exception.
  - `backend/scripts/backfill_seeded_timestamps.py` (new): scans
    every skill, finds any step with `start is None` OR `end is None`,
    probes the video duration via `ffprobe` when a `video_id`
    resolves to a GridFS blob (fallback: 60 s), then distributes
    steps evenly across that duration (`step i → start = (i-1)·D/N,
    end = i·D/N`). Preserves whichever of `start`/`end` was already
    set, so partially-timed skills aren't flattened. Idempotent.
  - Backfill run this pass:
    ```
    patched 1 skill(s):
      - 'Glove removal' (c60f1d3a): 7 steps across 60.0s → 8.57s/step
    ```
    Re-run → "nothing to backfill" (idempotent).
  - Regression: Glove `POST /skills/{id}/edit` → `PUT /draft` → `POST
    /publish` round-trip now returns `{"skill_id": ..., "version":
    N+1}` with zero blocking problems.

- **TWEAK-B follow-up (data-integrity bug caught during FIX B
  regression).** The first round-trip surfaced that
  `features/lessons/schemas.py::validate_analyze` was coercing every
  check id to `c{N}` — orphaning Lucia's reviewed Glove attempt
  (`6853fc06`), which references `g1..g7`. The validator now
  **preserves** any non-empty string id and demotes the mismatch to
  an informational `blocking: false` problem
  (`"Non-standard id 'gN' preserved (new skills prefer 'cN')."`). Only
  missing ids get the auto-assigned `c{N}`. The damaged state from
  the regression run was repaired in the same commit (checks +
  es/tl check arrays reverted to `g1..g7`; title restored to
  `"Glove removal"`).

- **FIX C — PUT /draft documented as a full replace.** `docs/CONTRACTS.md`
  now has a pinned **§1c — Lessons jobs endpoint shapes** section
  that enumerates `POST /skills/{id}/edit` (lazy handle), `GET
  /jobs/{job_id}` (synthesises for virgin / terminal-breadcrumb
  handles), `PUT /jobs/{job_id}/draft` (full replace, not merge —
  with the explicit warning that clients MUST send the complete
  draft), and `POST /jobs/{job_id}/publish` (post-publish wipe +
  virgin-handle 422). The schema blocks match what the frontend
  `DraftEditorPage` ships today.

- **Cleanup — tester orphans + a duplicate seed row.**
  - Deleted the tester's leftover `edit-c60f1d3a9c44493b8c5e2fd5d3644d82`
    row and the stale `82ad36cd…` published breadcrumb for the Glove
    skill (direct DB delete; `cleanup_orphan_drafts.py` doesn't sweep
    canonical lazy edit handles by design, so a one-off was correct).
  - Found + fixed a seed guard bug while here:
    `features/grading/seed.py::ensure_glove_removal_skill` was probing
    by `title == "Glove removal"` alone. If a Care Manager (or Batch-2
    smoke test) temporarily renames the skill in the editor, the next
    hot-reload re-ran the seed and inserted a second copy with a fresh
    `uuid4()`. The guard now probes by `source: "grading-feature-seed"`
    first and backfills the marker on legacy rows found by title. The
    stray duplicate `3aba461b…` was hard-deleted (no attempts /
    signoffs / cleared_skills referenced it); the canonical Glove row
    now carries the `source` marker so the next restart is a no-op.

### Batch 3 — Role switch functional gating (#15 / #16 / #17)

> **Not real auth.** The frontend sends `X-Firstshift-Role` from a
> `localStorage` value and the backend trusts it. A motivated user can
> forge the header by typing one line into dev tools. This is a
> hide-and-disable UX plus a server-side 403 on destructive flows, so
> no feature "silently works" from a role that shouldn't have it.
> Real auth replaces the header when it lands (`CONTRACTS §10`).

#### Full endpoint × role matrix (pinned)

| Endpoint                                                       | Care Manager | Trainer | Scheduler |
| -------------------------------------------------------------- |:------------:|:-------:|:---------:|
| `POST /api/grading/attempts/{id}/signoff`                      | ✅           | 403     | 403       |
| `POST /api/questions/{id}/answer`                              | ✅           | 403     | 403       |
| `POST /api/questions/transcribe`                               | ✅           | 403     | 403       |
| `POST /api/lessons/uploads`                                    | ✅           | ✅      | 403       |
| `PUT  /api/lessons/uploads/{id}/chunks/{n}`                    | ✅           | ✅      | 403       |
| `POST /api/lessons/uploads/{id}/complete`                      | ✅           | ✅      | 403       |
| `POST /api/lessons/jobs/{id}/retry`                            | ✅           | ✅      | 403       |
| `PUT  /api/lessons/jobs/{id}/draft`                            | ✅           | ✅      | 403       |
| `POST /api/lessons/jobs/{id}/steps/{n}/frame`                  | ✅           | ✅      | 403       |
| `POST /api/lessons/jobs/{id}/publish`                          | ✅           | ✅      | 403       |
| `POST /api/lessons/skills/{id}/edit`                           | ✅           | ✅      | 403       |
| `DELETE /api/lessons/skills/{id}` (archive)                    | ✅           | 403     | 403       |
| `POST /api/lessons/skills/{id}/unarchive`                      | ✅           | 403     | 403       |
| `PUT  /api/lessons/skills/{id}/translations/{lang}`            | ✅           | ✅      | 403       |
| `POST /api/lessons/skills/{id}/translations/{lang}/review`     | ✅           | ✅      | 403       |
| `POST /api/lessons/skills/{id}/translations/retry`             | ✅           | ✅      | 403       |

Every GET and every caregiver-side endpoint is open to any role.

#### 403 detail shape (pinned — frontend parses `.allowed`)

```jsonc
// Header missing or empty
{ "detail": { "reason": "role_required",     "allowed": ["Care Manager", "Trainer"] } }

// Header present but not in allow-set
{ "detail": { "reason": "role_not_allowed", "role": "Scheduler",
              "allowed": ["Care Manager", "Trainer"] } }
```

#### Backend mechanism — `backend/roles.py`

- `Role.{CARE_MANAGER, TRAINER, SCHEDULER}` string constants
- `AGENCY_ROLES` frozenset
- `require_role(allowed)` → FastAPI `Depends()` factory
  - Reads `X-Firstshift-Role` via `Header(default=None)` (FastAPI
    auto-maps `x_firstshift_role` → that header).
  - Raises `403` with the detail shape above on both missing + mismatch.
  - Returns the role string so endpoints can log who did what.

Each gated route adds `_role: str = Depends(_<name>_ROLE)` where the
`_ROLE` constants live at module top so the allow-set is visible at a
glance (`features/lessons/jobs.py::_JOB_WRITE_ROLE`,
`features/lessons/skills_routes.py::_EDIT_ROLE` + `_ARCHIVE_ROLE`,
`features/grading/routes_signoff.py::_SIGNOFF_ROLE`,
`features/questions/routes.py::_INBOX_WRITE_ROLE`,
`features/lessons/uploads.py::_UPLOAD_ROLE`).

#### Frontend mechanism

- `frontend/src/api.js`
  - Request interceptor: attaches `X-Firstshift-Role: <currentRole()>`
    on every outbound request. Agency-side pages always have a role in
    `localStorage`; caregiver-side requests are open on the server, so
    the header is harmless.
  - Response interceptor: on `403` with `detail.reason in {role_required,
    role_not_allowed}`, calls the shell-registered `onForbidden(payload)`.
    `setForbiddenHandler(fn)` is called by the shell at mount.
- `frontend/src/hooks/useRole.js`
  - `useRole()` returns the current role and re-renders on change
    (listens for `firstshift:role` custom event + native `storage`
    event). `writeRole(next)` writes localStorage AND dispatches the
    custom event so sibling pages update **live** when the switch flips.
  - Capability predicates (`canSignoff`, `canAnswerQuestions`,
    `canArchiveSkill`, `canEditSkill`, `canRecordSkill`) — one source
    of truth per role × action, mirrored in page UIs.
- `frontend/src/shell/Toasts.js` — minimal provider (bottom-centred
  stack, auto-dismiss 4.5 s, click-to-dismiss, 3 variants). Mounted
  inside `AgencyShell` via `<ToastProvider>`. A `ForbiddenToastBridge`
  component wires `setForbiddenHandler(useForbiddenToast())` at mount
  so a 403 renders:
    `Your role doesn't allow this action.` +
    `Allowed: Care Manager, Trainer.`

#### Per-page UI gating (what each role sees)

| Page / Component                       | Care Manager            | Trainer                                    | Scheduler                                          |
| -------------------------------------- | ----------------------- | ------------------------------------------ | -------------------------------------------------- |
| `/skills` (SkillsPage)                 | full                    | full                                       | list only; Record button hidden, drafts section hidden, one-line note |
| `/skills/<id>` (SkillDetailPage)       | full + Edit + Archive   | full + Edit (no Archive)                   | full read-only (no Edit, no Archive)               |
| `/skills/record` (RecordPage)          | editor                  | editor                                     | gate card ("Switch to Care Manager or Trainer…")   |
| `/skills/drafts/<id>` (DraftEditor)    | editor                  | editor                                     | gate card                                          |
| `/signoff` (SignoffPage)               | full queue              | full queue (buttons disappear on detail)   | full queue (same)                                  |
| `/signoff/<id>` (SignoffDetailPage)    | full (approve, send\_back) | video + checks visible; approve/send\_back replaced with `signoff-role-gate` card | same as Trainer |
| `/competency/<id>` (CompetencyDetail)  | full                    | full                                       | full                                               |
| `/questions` (QuestionsPage inbox)     | full (answer + record)  | list + waiting + answered visible; answer form replaced with `question-detail-role-gate` card | same as Trainer |

Scheduler keeps **full access** to Today, Clients and New-hires pages
(all `ops/` endpoints are still placeholders — Batch-3 does not block
them).

#### DONE WHEN evidence — Batch 3

Backend (every row verified):

```
# Scheduler trying any lesson write → 403 role_not_allowed
curl -s -X POST  "$API/api/lessons/skills/$ID/edit"      -H "X-Firstshift-Role: Scheduler"
curl -s -X DELETE "$API/api/lessons/skills/$ID"           -H "X-Firstshift-Role: Scheduler"
curl -s -X POST  "$API/api/lessons/jobs/edit-$ID/publish" -H "X-Firstshift-Role: Scheduler"
curl -s -X PUT   "$API/api/lessons/jobs/edit-$ID/draft"   -H "X-Firstshift-Role: Scheduler" ...

# Trainer trying signoff / answer / archive → 403 role_not_allowed
curl -s -X POST   "$API/api/grading/attempts/$AID/signoff" -H "X-Firstshift-Role: Trainer"
curl -s -X POST   "$API/api/questions/$QID/answer"         -H "X-Firstshift-Role: Trainer"
curl -s -X DELETE "$API/api/lessons/skills/$ID"            -H "X-Firstshift-Role: Trainer"

# No header → 403 role_required
curl -s -X POST "$API/api/lessons/skills/$ID/edit"

# Allowed role → 200
curl -s -X POST "$API/api/lessons/skills/$ID/edit"      -H "X-Firstshift-Role: Trainer"       → {"job_id":"edit-..."}
curl -s -X POST "$API/api/lessons/skills/$ID/edit"      -H "X-Firstshift-Role: Care Manager"  → {"job_id":"edit-..."}

# READ endpoints have no gate (regression)
curl -s          "$API/api/lessons/skills"
curl -s -X POST  "$API/api/questions/ask" -H "Content-Type: application/json" -d '{"caregiver_id":"x","text":"y"}'  → 200
```

Frontend (observed via Playwright screenshot run):

```
# Role switch is reactive — flipping the select on /skills/<id>
# updates sibling buttons within one tick (no reload).
scheduler  → edit-btn=0 archive-btn=0
trainer    → edit-btn=1 archive-btn=0
care mgr   → edit-btn=1 archive-btn=1

# /signoff/<id> — approve button vanishes mid-form when role flips
# to Trainer, and the signoff-role-gate card replaces the actions box.
```

#### Known limits (deliberate — document in CONTRACTS when real auth lands)

- Role string is client-declared via `localStorage.getItem('firstshift.agency_role')`.
- Nothing stops a user from editing the header in dev tools and
  bypassing the server gate — this is NOT a security boundary.
- Real auth is the plan; the header approach keeps the API surface
  stable so swapping auth later is a header-source change, not a
  schema change.

