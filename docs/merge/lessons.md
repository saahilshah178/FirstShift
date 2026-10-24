# Merge notes — `lessons/record`

> Branch: `lessons/record`, forked off `main`.
> Scope: "Record a skill" (Care Manager): upload → transcode → analyze → draft → publish → translate.

## Files added

### Backend (`backend/features/lessons/`)
- `uploads.py`     — chunked upload (`POST /uploads`, `PUT /uploads/{id}/chunks/{i}`, `POST /uploads/{id}/complete`).
- `jobs.py`        — job + draft endpoints (`GET /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/retry`,
                     `PUT /jobs/{id}/draft`, `POST /jobs/{id}/steps/{n}/frame`, `POST /jobs/{id}/publish`).
- `skills_routes.py` — published skill endpoints (`GET /skills/{id}`, `POST /skills/{id}/edit`,
                       `PUT /skills/{id}/translations/{lang}`, review + retry).
- `transcode.py`   — ffprobe + ffmpeg wrappers.
- `pipeline.py`    — analyze stage: `call_gemini` + validation + retry.
- `translate.py`   — publish-time es/tl translation pipeline (idempotent).
- `runner.py`      — in-process asyncio job runner + heartbeat + stale sweep.
- `schemas.py`     — lane-B Gemini response schema + validators.

### Frontend (`frontend/src/features/lessons/`)
- `SkillsPage.js`           — rewritten: published skills + in-progress jobs + "Record a skill".
- `RecordPage.js`           — upload page with local size/duration pre-check and chunked POST.
- `DraftEditorPage.js`      — `/skills/drafts/:jobId` — stage view + editor + publish.
- `SkillDetailPage.js`      — `/skills/:skillId` — English + es/tl tabs, Edit, Mark reviewed.
- `routes.js`               — adds `/skills/record`, `/skills/drafts/:jobId`, `/skills/:skillId`
                              (keeps existing `/skills` and `/c/:code/lessons`).

### Docs
- `docs/merge/lessons.md` (this file).

## Shared lines changed

**Zero.** Auto-discovery (both sides) picks up the new files without any central registry edits.
`requirements.txt` is **unchanged**; the pod already ships `ffmpeg 5.1.9` and `ffprobe 5.1.9`,
so `imageio-ffmpeg` was not added.

## Endpoints (prefix `/api/lessons`)

| Method | Path                                                 | Purpose |
| ------ | ---------------------------------------------------- | ------- |
| POST   | `/uploads`                                           | init: `{filename,size,content_type}` → `{upload_id,chunk_size}` (413/415) |
| PUT    | `/uploads/{upload_id}/chunks/{index}`                | raw-bytes chunk upload |
| POST   | `/uploads/{upload_id}/complete`                      | `{source_credit?}` → `{job_id}` (415/422); kicks runner |
| GET    | `/jobs`                                              | list drafts & in-progress jobs |
| GET    | `/jobs/{job_id}`                                     | job state incl. draft, problems, draft_rev |
| POST   | `/jobs/{job_id}/retry`                               | resume from first incomplete stage |
| PUT    | `/jobs/{job_id}/draft`                               | `{draft,source_credit,draft_rev}` → re-validate (409 on stale rev) |
| POST   | `/jobs/{job_id}/steps/{n}/frame`                     | regenerate a step's still frame |
| POST   | `/jobs/{job_id}/publish`                             | atomic ready→publishing, writes skill, translates (409/422) |
| POST   | `/skills/{skill_id}/edit`                            | create a new draft job copied from published skill |
| GET    | `/skills/{skill_id}`                                 | full skill doc |
| PUT    | `/skills/{skill_id}/translations/{es\|tl}`           | save edited translation text |
| POST   | `/skills/{skill_id}/translations/{es\|tl}/review`    | mark translation reviewed |
| POST   | `/skills/{skill_id}/translations/retry`              | re-run translate pipeline |

All appear in `/api/openapi.json`.

**Preserved byte-identical** (as required):
- `GET /api/lessons/`
- `GET /api/lessons/skills`
- `GET /api/lessons/caregiver/{caregiver_id}`

## New fields & defaults

### `lesson_jobs` (new collection, owned by this feature)
```
{_id: uuid4hex,
 status: "uploading"|"converting"|"analyzing"|"extracting_frames"|"ready"
         |"publishing"|"published"|"failed",
 error: "",                 # one-line human message
 video_id: null,            # MediaStore uuid of the compressed original
 source_credit: "",
 skill_id: null,            # populated on publish
 draft: {title, steps, checks, quiz},
 problems: [],              # [{where, message}] when validation yielded warnings
 draft_rev: 0,              # bumped on every PUT /draft and runner mutation
 heartbeat_at: ISO-8601,    # updated every 5 s while a stage is running
 created_at: ISO-8601,
 updated_at: ISO-8601}
```

### `skills` (additive fields; defaults listed; existing fields untouched)
- `version: int`        — default `1` (missing = 1).
- `source_credit: str`  — default `""`.
- `video_id: str|null`  — default `null`.
- `translations.<es|tl>` gains:
  - `checks: [{id, description}]`
  - `quiz:   [{id, prompt, choices}]`
  - `status: "machine"|"reviewed"|"stale"` (missing = `"machine"`)

Existing `title`, `steps[{n,title,instruction}]`, `checks`, `quiz` shapes stay as they are.

### Hand-off for grading lane
- **`attempts.skill_version`** — grading-lane field, **not written here**. Suggested default
  `null`; grading should snapshot the skill's current `version` when an attempt starts and warn
  if versions differ at sign-off (restart from step 1).

## Env keys

| Key                           | Required | Notes                                                 |
| ----------------------------- | -------- | ----------------------------------------------------- |
| `GEMINI_API_KEY`              | yes      | existing — unchanged                                  |
| `GEMINI_MODEL`                | no       | existing — defaults to `gemini-3.5-flash`             |
| `LESSONS_FORCE_FAIL_STAGE`    | no       | **test-only** — set to `converting`/`analyzing`/`extracting_frames`/`publishing` to force that stage to raise. Unset in prod. |

## Risks / known limits

- **No backend auth** (CONTRACTS §10 TODO). The Care Manager gate is UI-only — any client
  that sets `firstshift.agency_role = "Care Manager"` in `localStorage` can reach these screens.
  Real auth is a later phase.
- A manual `python -m backend.seed.seed` **wipes published skills** (seed owns the `skills`
  collection — see CONTRACTS §7). Document for operators; don't re-seed between recordings
  you want to keep.
- **Media retention TODO** — nothing deletes the compressed-original `video_id` or the step
  frame_ids when a draft is discarded. Belongs with the signed-media-tokens phase.
- `GET /api/media/{uuid}` is still publicly readable (CONTRACTS §10 TODO).

## Caregiver-side handoff (for `caregivers/lessons` lane)

- Show `source_credit` next to the skill title when present.
- For safety-critical checks, display the English text next to the es/tl translation whenever
  `translations.<lang>.status !== "reviewed"`. Discoverable from `GET /skills/{id}`.

## Known UX quirks

- Draft `draft_rev` conflict returns **409** (correct). Publish on a draft with no steps/checks
  returns **422** with the specific reasons.
- Translate failures surface as `translations.<lang>.status === "stale"` with a `Retry
  translation` button; English publish is **not** rolled back.

## Prep step for DONE WHEN "Transfer" clip

The user-provided Transfer clip is a 1080p lecture ≥2:00. For the acceptance run it was
trimmed to the first 115 seconds via re-encode (not stream-copy) so the extracted frames
are seekable in the editor:

```
ffmpeg -i transfer.mp4 -t 115 -vf scale=1280:-2 -c:v libx264 -crf 23 \
       -c:a aac -b:a 96k /tmp/transfer_short.mp4
```

## 3-step manual test

1. **Record a skill (happy path)**
   - Set `localStorage.firstshift.agency_role = "Care Manager"`, visit `/skills`,
     click "Record a skill", pick a ≤2:00 mp4 (ex: `transfer_short.mp4`),
     set source credit, Upload.
   - On `/skills/drafts/:jobId`, watch the stage list advance: Converting → Analyzing
     → Extracting frames → Ready.
   - Confirm each step card shows an inline frame image and sensible instruction text.
   - Click Publish → redirects to `/skills/:skillId`.
2. **Translations**
   - On the skill detail page, click the `es` tab → "Machine-translated" badge visible,
     counts of steps / checks / quiz match English.
   - Same for `tl`.
   - Click `Mark reviewed` on `es` → badge disappears, status becomes `reviewed`.
3. **Edit → republish**
   - Click `Edit skill`, open the new draft, change one step's instruction, Publish.
   - Back on the skill page: version is `2`; the edited step's `es`/`tl` text changed,
     other steps' translations stay the same text as before.

See **"DONE WHEN evidence"** section (filled in after acceptance run).

## DONE WHEN evidence (Transfer-clip acceptance run)

All curls below hit the preview deployment at
`BASE=https://shift-backbone.preview.emergentagent.com`.

**Prep step.** The user-provided Transfer clip is a 233 s 1080p lecture;
I trimmed to 115 s via re-encode (short-side 720 later during convert) so
the extracted frames are seekable:

```
ffmpeg -y -ss 85 -i transfer.mp4 -t 115 -vf scale=1280:-2 \
       -c:v libx264 -crf 23 -preset veryfast \
       -c:a aac -b:a 96k /tmp/transfer_mid.mp4
# duration: 115.015 s
```

The 85 s offset was chosen so the clip spans the actual bed-to-wheelchair
transfer sequence (gait-belt → chair placement → stand → pivot → brake
release). A 0 s-offset trim misses the brake-release step entirely.

### 1 — Upload reaches `ready` through staged status

| job_id | `ba7d2af92aa243c4aa711425f3d1eec5` |
| ------ | ---------------------------------- |
| source_credit | `"Chippewa Valley Technical College, CC BY 4.0, edited"` |
| timings | `0 → 10 s converting`, `10 → 22 s analyzing`, `22 → 24 s extracting_frames`, `24 s ready` |
| final status | `ready` with `duration_s=115.015` |

### 2 — Draft as generated (zero manual edits)

```
steps: 5
  1. Apply the Gait Belt                       [0.0 – 26.0]   frame_id=3ad0bc47aed643ef9312e7826de604f2
  2. Prepare the Wheelchair                    [26.0 – 65.0]  frame_id=022da04522aa4154bede11c1f9130a86
  3. Assist Patient to Stand                   [65.0 – 91.0]  frame_id=93167576652f4fdda324c32253dbb41f
  4. Transfer Patient to Wheelchair            [91.0 – 101.0] frame_id=59c90f776e68408c8251c838348331ac
  5. Remove Belt and Release Brakes            [101.0 – 115.0] frame_id=b0c57ca8fbe44b528dfba7630bdff7d4

checks: 5
  c1  (SAFETY) Gait belt is fastened securely around patient's waist.
  c2          Foot pedals are removed from the wheelchair before transfer.
  c3  (SAFETY) Wheelchair brakes are engaged and locked.        ← the signal check
  c4  (SAFETY) Nurse places feet directly in front of patient's feet to prevent slipping.
  c5          Patient grasps armrests while sitting down into wheelchair.

quiz: 2 × 3 options with answer_index
  q1 "How tight should the gait belt be fastened..." → answer_index=2 ("two fingers")
  q2 "How should the nurse grip the gait belt..."     → answer_index=0 ("fingertips facing upward")
```

All 5 `GET /api/media/<frame_id>` returned `HTTP 200 image/jpeg` (65–82 KB each).

### 3 — Publish → skill shape

- `GET /api/lessons/skills/c7691d94cef347f6bc03f3fc808939bd` →
  `version=1`, `source_credit` present, both `translations.es` and
  `translations.tl` with `status="machine"`, 5 steps/5 checks/2 quiz
  (all counts match English).
- Spanish title: `"Transferencia de un paciente de la cama a la silla de ruedas con cinturón de marcha"`
- Tagalog title: `"Paglilipat ng Pasyente mula sa Kama Patungong Silya de Roda Gamit ang Gait Belt"`
- Listed in `GET /api/lessons/skills` as `step_count=5, check_count=5`.

### 4 — Edit → republish → selective retranslation

Edited step 1 instruction only → republished. v2 skill:

- `version=2`.
- English step 1 instruction changed; steps 2–5 english text identical.
- `translations.es.steps[0]` and `translations.tl.steps[0]` changed;
  other `es`/`tl` step texts byte-identical to v1 translations.
  _(Verified by snapshotting v1 before edit and diffing field-by-field —
  the `_diff_items` function compares current English vs previously-
  published English, not vs the prior translation.)_

Second edit (step 2 title) → `version=3`, only step 2 translation changed.

### 5 — Failures

| scenario | result |
| -------- | ------ |
| `POST /uploads` with `size=315000000` | `HTTP 413 {"detail":"File exceeds 314572800 bytes."}` |
| `POST /uploads` with `content_type="application/x-msdownload"` | `HTTP 415 {"detail":"Unsupported content-type: 'application/x-msdownload'"}` |
| `POST /uploads/{id}/complete` with a 150 s video | `HTTP 422 {"detail":"Video is longer than 2 minutes"}` |
| `LESSONS_FORCE_FAIL_STAGE=analyzing` + fresh upload | job → `failed`, `error="forced failure (LESSONS_FORCE_FAIL_STAGE=analyzing)"` in 10 s |
| Unset env + `POST /jobs/{id}/retry` | reached `ready` in 14 s (convert stage skipped — `video_id` reused) |
| `supervisorctl restart backend` while a job was in `analyzing` | 16 s later, next `GET /jobs/{id}` flipped the row to `failed`, `error="Interrupted (server restart)"` (lazy sweep + `heartbeat_at` > 30 s) |
| Retry after interrupt | reached `ready` in 16 s |

### 6 — Preserved shapes

- `GET /api/lessons/skills` → still returns `{skills:[{id,title,step_count,check_count}]}`;
  the 4 seeded skills (Transfer from bed to wheelchair, Hand hygiene,
  Blood pressure measurement, Glove removal) are listed alongside the new
  one.
- `GET /api/lessons/caregiver/{caregiver_id}` → still returns
  `{caregiver:{id,name}, cleared:[{id,title,step_count}], remaining:[...]}`.
  Confirmed on caregiver `Alex Johnson` (code `2TBAFX`).

## Shared-line changes

Zero. `requirements.txt` unchanged (ffmpeg system binary already installed on the pod).

