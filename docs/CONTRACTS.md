# FirstShift — Contracts

> This document is the fork-safety contract. If you change anything here,
> you are changing the shape every other branch depends on.

## 1. Backend auto-discovery (features)

At startup, `backend/server.py` walks `backend/features/` with
`pkgutil.iter_modules` and imports every subpackage. If a subpackage
exposes a module-level `router: fastapi.APIRouter`, it is mounted at
`/api/<subpackage_name>`.

**Rules a feature package must follow:**

- Live at `backend/features/<name>/__init__.py` (or any Python package
  structure, so long as `backend.features.<name>` exposes `router`).
- Expose `router: APIRouter`.
- A feature import failure is logged and *skipped* — it never crashes
  the app. Guard your top-level imports accordingly.
- Mount prefix is `/api/<name>`; `<name>` is the folder name verbatim.

Current features: `ops`, `lessons`, `grading`, `questions`, `channel`,
`caregivers`.

### Backend endpoints per feature

(Only Phase-2 agency/caregiver shell endpoints are listed; placeholder
`GET /` on every feature still returns `{"feature":"<name>","status":"placeholder"}`.)

| Endpoint                                   | Returns                                                          |
| ------------------------------------------ | ---------------------------------------------------------------- |
| `GET /api/ops/caregivers`                  | `{caregivers:[…]}` with projected fields. Query: `?sort=hired_at_desc` for New-Hires view. |
| `GET /api/ops/clients`                     | `{clients:[{id,agency_id,name,required_skills:[{id,title}]}]}` |
| `GET /api/lessons/skills`                  | `{skills:[{id,title,step_count,check_count}]}`                   |
| `GET /api/lessons/caregiver/{caregiver_id}`| `{caregiver,cleared:[],remaining:[]}`                            |
| `GET /api/grading/attempts`                | `{attempts:[{id,caregiver,skill,overall,clip_id,check_results[]}]}` |
| `GET /api/grading/competency`              | `{caregivers:[{id,name,cleared_count,cleared[]}],total_skills}` |
| `GET /api/questions/list`                  | `{questions:[…]}` — row shape see **§1b — Questions endpoint shapes** below. |
| `POST /api/questions/ask`                  | See **§1b**.                                                      |
| `POST /api/questions/{question_id}/answer` | See **§1b**. Body field is `text` (not `answer`).                 |
| `POST /api/questions/transcribe`           | See **§1b**.                                                      |
| `GET /api/questions/inbox`                 | See **§1b**.                                                      |
| `GET /api/questions/policies`              | See **§1b**.                                                      |
| `GET /api/caregivers/list`                 | See **§1a — Caregivers endpoint shapes** below.                   |
| `GET /api/caregivers/by-code/{code}`       | See **§1a — Caregivers endpoint shapes** below. Code is upper-cased server-side. |

### 1a. Caregivers endpoint shapes (pinned)

Forks must not have to read source to learn these.

#### `GET /api/caregivers/list` → `200`

```jsonc
{
  "caregivers": [
    {
      "id":              "<string: _id, uuid4 hex>",
      "name":            "<string>",
      "language":        "en" | "es" | "tl",
      "access_code":     "<string: 6 chars, [A-HJ-KM-NP-Z2-9]>",
      "agency_id":       "<string>",
      "agency_name":     "<string: joined from agencies collection>",
      "hired_at":        "<string: ISO-8601>",
      "experience_note": "<string>",
      "cleared_skills":  ["<skill_id>", ...]
    }
    // ... sorted by `name` ascending
  ]
}
```

The outer `{"caregivers": [...]}` wrapper is intentional so we can
add pagination fields later without breaking callers.

#### `GET /api/caregivers/by-code/{code}` → `200` or `404`

- `code` is normalised server-side (`.strip().upper()`), so
  `/by-code/zspusg` and `/by-code/ZSPUSG ` both resolve.
- `404 {"detail": "caregiver not found"}` when no caregiver matches.
- On success:

```jsonc
{
  "caregiver": {
    "id":              "<string>",
    "name":            "<string>",
    "language":        "en" | "es" | "tl",
    "access_code":     "<string: 6 chars>",
    "agency_id":       "<string>",
    "hired_at":        "<string: ISO-8601>",
    "experience_note": "<string>",
    "cleared_skills":  ["<skill_id>", ...]
  },
  "agency": {
    "id":   "<string>",
    "name": "<string>"
  }   // or null if the caregiver has no agency (should not happen in seed data)
}
```

Notes for forks:

- `caregiver.id` is the same string value stored as `_id` in Mongo
  (uuid4 hex, not an `ObjectId`).
- `caregiver` here **omits** `agency_name` because `agency.name` is
  returned separately. In `/list` the fields are flattened for picker
  convenience; in `/by-code/:code` they're nested so a caregiver
  context can expose `{caregiver, agency}` without duplication.
- `cleared_skills` is always an array (possibly empty), never `null`.

### 1b. Questions endpoint shapes (pinned)

Added on branch `channel/questions`. Forks must not have to read source
to learn these.

#### `GET /api/questions/list` → `200`

Preserved from Phase-1 shape; row keys documented here for the first time:

```jsonc
{
  "questions": [
    {
      "caregiver_id": "<string>",
      "text":         "<string>",       // the question
      "language":     "en" | "es" | "tl",
      "status":       "waiting_owner" | "answered",
      "answer":       "<string|null>",  // null while waiting
      "card_id":      "<string|null>",  // set when answered against a card
      "source":       "owner" | "card" | "ai",
      "created_at":   "<string: ISO-8601>",
      "answered_at":  "<string: ISO-8601|null>"   // null while waiting
    }
  ]
}
```

#### `POST /api/questions/ask` → `200`

Request body: `{"caregiver_id": "<id>", "text": "<question>"}`.
Response shape:

```jsonc
{
  "question_id":  "<string>",
  "caregiver_id": "<string>",
  "question":     "<string>",
  "status":       "answered" | "waiting_owner",     // NEW on this branch
  "answer":       "<string>",                       // "" when waiting_owner
  "citations":    [{ "source_title": "<string>" }], // [] when waiting_owner
  "confidence":   0.0..1.0,                         // 0.0 when waiting_owner
  "answered_at":  "<string: ISO-8601|null>",        // null when waiting_owner
  "model":        "gemini" | "stub"
}
```

#### `POST /api/questions/{question_id}/answer` → `200` or `404` / `409` / `422`

> **Body field is `text`, not `answer`.** It carries the text content of
> the manager's answer. We kept the name consistent with the `text` field
> on `question` rows (both describe the "written content" of the
> underlying utterance). This differs from the original brief which said
> `{"answer": "..."}`.

Request body: `{"text": "<string>"}` (required, non-empty).
Responses:

```jsonc
// 200
{ "question_id": "<string>",
  "card_id":      "<string>",   // the card that was created
  "delivered_text": "<string>"  // the message as delivered to the caregiver
                                // (translated when caregiver.language != 'en')
}
// 404 { "detail": "question not found" }
// 409 { "detail": "question already answered" }
// 422 { "detail": "answer text required" | "text required" }
```

#### `POST /api/questions/transcribe` → `200` or `413` / `415`

Multipart form:
- `file` — audio clip, one of `audio/webm`, `audio/mpeg`, `audio/wav`,
  `audio/aac`, `audio/ogg`. ≤25 MB.

```jsonc
{ "media_id": "<string>",       // uuid4 hex of the stored audio in GridFS
  "transcript": "<string>" }    // empty when the clip has no speech
```

#### `GET /api/questions/inbox` → `200`

```jsonc
{
  "waiting":  [ /* InboxRow */ ],
  "answered": [ /* InboxRow */ ],
  "total":    <int>
}
// InboxRow:
{
  "id":           "<string>",
  "caregiver":    { "id": "<string>", "name": "<string>", "language": "en|es|tl" },
  "text":         "<string>",
  "language":     "en|es|tl",
  "status":       "waiting_owner" | "answered",
  "answer":       "<string|null>",
  "source":       "owner" | "card" | "ai",
  "card_id":      "<string|null>",
  "created_at":   "<string: ISO-8601>",
  "answered_at":  "<string: ISO-8601|null>"
}
```

#### `GET /api/questions/policies` → `200`

```jsonc
{ "policies": [ { "id": "<string>", "title": "<string>", "text": "<string>" } ] }
```

### 1c. Lessons jobs endpoint shapes (pinned)

> Pinned in Batch-2 tightening after a tester hand-crafted a partial
> `PUT /draft` payload and was surprised when the stored draft got
> replaced wholesale. The frontend `DraftEditorPage` always sends the
> whole draft on every save — any fork that reuses this contract
> MUST do the same.

#### `POST /api/lessons/skills/{skill_id}/edit` → `200`

```jsonc
{ "job_id": "edit-<skill_id>" }
```

Deterministic, idempotent, **and lazy**: this call does NOT insert a
`lesson_jobs` row. The row materialises on the first successful
`PUT /jobs/{job_id}/draft`. See `backend/scripts/cleanup_orphan_drafts.py`
for how abandoned handles are swept.

#### `GET /api/lessons/jobs/{job_id}` → `200`

Returns the current job state. For a lazy edit handle
(`job_id = "edit-<skill_id>"`) where no row exists yet, OR where the
only row is a terminal `published` breadcrumb from a prior session,
the response is **synthesised from the current published skill** with
`draft_rev: 0`. Callers cannot distinguish synthetic from real on the
wire — that's by design.

```jsonc
{
  "id":            "<string: job_id>",
  "status":        "<string: converting|analyzing|extracting_frames|ready|publishing|published|failed>",
  "error":         "<string>",
  "video_id":      "<string|null>",
  "source_credit": "<string>",
  "skill_id":      "<string|null>",
  "duration_s":    "<number: seconds>",
  "draft": {
    "title":  "<string>",
    "steps":  [ { "n": "<int>", "title": "<string>", "instruction": "<string>",
                  "start": "<number: seconds>", "end": "<number: seconds>",
                  "frame_id": "<string|null>" } ],
    "checks": [ { "id": "<string>", "description": "<string>", "safety_critical": "<bool>" } ],
    "quiz":   [ { "id": "<string>", "prompt": "<string>",
                  "choices": [ "<string>", "<string>", "<string>" ],
                  "answer_index": "<int: 0..2>" } ]
  },
  "problems":   [ { "where": "<string>", "message": "<string>", "blocking": "<bool>" } ],
  "draft_rev":  "<int>",
  "created_at": "<string: ISO-8601>",
  "updated_at": "<string: ISO-8601>"
}
```

#### `PUT /api/lessons/jobs/{job_id}/draft` → `200`

**FULL REPLACE of the stored draft** (standard REST PUT semantics —
NOT a merge/patch). The server validates the shape with
`features/lessons/schemas.py::validate_analyze`, re-attaches
`steps[].frame_id` from the client payload (the validator strips
them), writes the new draft, and returns the fresh job state.

Clients MUST always send the complete `draft` object. Sending a
partial draft replaces the stored draft with just those fields.

```jsonc
// Request body
{
  "draft":         { /* full Draft shape; see GET above */ },
  "draft_rev":     "<int: must match the server's current value>",
  "source_credit": "<string: optional; omit to leave unchanged>"
}
```

- `draft_rev` mismatch → `409 "draft_rev stale (got X, have Y)"`.
- First save of a lazy handle (`edit-<skill_id>`) requires
  `draft_rev: 0`; the handler materialises the row from the
  published skill then applies the save.
- Status `published` → `409 "published; use /skills/{id}/edit"`.

#### `POST /api/lessons/jobs/{job_id}/publish` → `200 | 422`

```jsonc
// 200
{ "skill_id": "<string>", "version": "<int>" }

// 422 (publish-not-ready; `reasons` is a flat list of human strings)
{ "detail": { "reasons": [ "<string>", "..." ] } }
```

**Post-publish wipe**: every `lesson_jobs` row with `skill_id` equal to
the just-published skill is deleted. The published skill (`version`
bump + `translations`) IS the audit trail. The draft drawer stays clean.

Virgin lazy handles that have never been saved → `422 "No changes to
publish — edit something first."` (same `detail.reasons` shape).

## 2. Frontend auto-discovery (features)

`src/featureRegistry.js` uses `require.context('./features', true, /\/routes\.js$/)`
(CRA/webpack built-in). **Not** `import.meta.glob` (that would require
migrating to Vite). No file in the app imports features by name.

**A feature's `routes.js` must export:**

```js
export const routes = [
  { path: "/<some-agency-path>", element: <SomeAgencyPage /> },
  { path: "/c/:code/<some-caregiver-path>", element: <SomeCaregiverPage /> },
];

export const nav = [
  { label: "…", path: "/<path>",         order: 10, side: "agency"    },
  { label: "…", path: "/c/:code/<path>", order: 10, side: "caregiver" },
];
```

### Nav manifest fields

| field   | type                             | notes                                                 |
| ------- | -------------------------------- | ----------------------------------------------------- |
| `label` | string                           | human-readable, used as the tab/pill text.            |
| `path`  | string                           | React-Router pattern. Caregiver paths include `:code`.|
| `order` | number                           | ascending sort within a side.                         |
| `side`  | `"agency" \| "caregiver"`        | determines which shell renders it.                    |

### Routing split (how the shell consumes the manifest)

- Any route whose path starts with `/c/:code` is mounted **under
  `<CaregiverLayout>`** (relative subpath; the layout extracts `:code`
  from the URL and exposes `{caregiver, agency, code}` via
  `useCaregiver()`).
- Every other route is mounted under `<AgencyShell>`.
- The agency root `/` **redirects** to `/today` (the default view).

### Agency role switch

- Three roles: `"Care Manager"`, `"Trainer"`, `"Scheduler"`.
- Persisted in `localStorage` under key **`firstshift.agency_role`**.
- Phase 2 does not gate behavior on the role — the dropdown is purely
  visible state for later phases to key off.

## 3. Service stubs (`backend/services/`)

Each stub returns realistic *fake* data today. Teammate branches will
later swap each body to call `backend/ai/gemini.py::call_gemini`.

### `grade_clip(skill_id, caregiver_id, clip_id) -> dict`
```jsonc
{ "skill_id": "...", "caregiver_id": "...", "clip_id": "...",
  "checks": [{ "id":"c1","description":"...",
               "result":"pass"|"fail"|"unclear",
               "time": 3.2, "seen": true, "safety_critical": true }],
  "overall": "pass"|"fail"|"needs_review", "score": 0.0..1.0,
  "created_at": "ISO-8601", "model": "stub" }
```

### `build_lesson(video_id) -> dict`
```jsonc
{ "video_id":"...", "title":"...",
  "steps":[{"n":1,"title":"...","instruction":"...",
            "start":0.0,"end":4.0,"frame_id":"<uuid>"}],
  "checks":[{"id":"...","description":"...","safety_critical":true}],
  "quiz":[{"id":"...","prompt":"...","choices":["..."],"answer_index":0}],
  "translations":{"es":{...},"tl":{...}},
  "model":"stub" }
```

### `send_message(caregiver_id, text, media_url=None) -> dict`
```jsonc
{ "message_id":"uuid4-hex","caregiver_id":"...",
  "text":"...","media_url":null,
  "status":"queued"|"sent"|"failed",
  "provider":"stub","sent_at":"ISO-8601" }
```

### `answer_question(caregiver_id, text) -> dict`
```jsonc
{ "question_id":"uuid4-hex","caregiver_id":"...",
  "question":"...","answer":"...",
  "citations":[{"skill_id":"...","step_n":1,"snippet":"..."}],
  "confidence":0.0..1.0,"answered_at":"ISO-8601","model":"stub" }
```

### `build_plan(caregiver_id, note_text) -> dict`
```jsonc
{ "plan_id":"uuid4-hex","caregiver_id":"...","note":"...",
  "items":[{"skill_id":"...",
            "action":"review"|"reattempt"|"shadow",
            "due_in_days":2,"reason":"..."}],
  "created_at":"ISO-8601","model":"stub" }
```

## 4. `MediaStore` (`backend/media/store.py`)

GridFS-backed, single interface:

```python
class MediaStore:
    async def save(self, file_bytes: bytes, content_type: str,
                   filename: str | None = None) -> str
    async def get(self, uuid_str: str) -> tuple[AsyncIterator[bytes], str, str]
```

- UUIDs are opaque (`uuid4().hex`).
- `get()` raises `FileNotFoundError` on unknown UUIDs; HTTP layer → 404.
- GridFS bucket name: `"media"`.

### HTTP

- `POST /api/media` — multipart form, field `file`.
  - Allowed: `video/mp4`, `video/quicktime`, `video/webm`, `audio/mpeg`,
    `audio/wav`, `audio/webm`, `image/jpeg`, `image/png`, `image/webp`.
  - Max 50 MB → `413`. Bad content type → `415`.
  - **Response (POLISH-A, Phase 2 start):** `url` is now a **relative
    path** — `"/api/media/<uuid>"`. The frontend prepends
    `REACT_APP_BACKEND_URL`; Twilio and similar providers can prepend
    the production host themselves. Do not hard-code the host anywhere.
- `GET /api/media/{uuid}` — streams the blob; 404 on missing.

> **TODO (later phase):** media access will require signed tokens — the
> stable integration point is the `url` field, not the raw UUID path.

## 5. Gemini helper (`backend/ai/gemini.py`)

```python
async def call_gemini(
    prompt: str,
    media_uuids: list[str] = [],
    response_schema: dict | None = None,
    fps: int | None = None,
) -> dict
```

- Pulls each `media_uuids[*]` from GridFS.
- Video blobs **> 20 MB** are uploaded via `client.files.upload`, polled
  until `state == ACTIVE` (timeout ~60 s), then referenced. Smaller
  blobs are sent inline.
- `response_schema` → structured JSON output; parsed dict is returned.
- Without `response_schema` → `{"text": "<raw response>"}`.
- **POLISH-B (Phase 2 start):** on `503 UNAVAILABLE` the helper retries
  **up to 2 times** with 1 s then 3 s backoff. If every attempt fails,
  the final `ServerError` propagates and `/api/ai/health` returns 503
  as before.
- Key: `GEMINI_API_KEY` env var. Missing → `/api/ai/health` returns 503
  with `{"ok": false, "error": "GEMINI_API_KEY is not set"}`. Does not
  crash the app.
- Model default: `gemini-3.5-flash` (override via `GEMINI_MODEL`).

### Health

- `GET /api/ai/health` — generates a tiny solid-color PNG, saves it via
  `MediaStore`, then calls `call_gemini` with
  `response_schema={"type":"object","properties":{"color":{"type":"string"}},"required":["color"]}`.
  Returns `{"ok": true, "model": "...", "result": {"color":"…"}}` on
  success, `503 {"ok": false, "error": "..."}` on failure.

## 6. MongoDB collections

All collections are created at startup. Only index:
`caregivers.access_code` **unique sparse**. Fifteen collections total
(ten originally seeded + `conversations`, `messages`, `cards`,
`policies` from channel/questions + `lesson_jobs` from lessons/record).

Access codes: 6 chars from `ABCDEFGHJKMNPQRSTUVWXYZ23456789` (no
`0`,`O`,`1`,`I`,`L`). Generation + insert goes through
`backend/util/access_code.py::retry_on_duplicate`.

| Collection   | Fields                                                                                                                                                                                                      |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `agencies`   | `_id`, `name`, `created_at`                                                                                                                                                                                 |
| `caregivers` | `_id`, `agency_id`, `name`, `language` (`'en'`\|`'es'`\|`'tl'`), `hired_at`, `experience_note`, `cleared_skills: [skill_id]`, `access_code: str` (6 chars, unique), `created_at`                            |
| `clients`    | `_id`, `agency_id`, `name`, `required_skills: [skill_id]`                                                                                                                                                   |
| `skills`     | `_id`, `title`, `steps: [{n,title,instruction,start,end,frame_id}]`, `checks: [{id,description,safety_critical:bool}]`, `quiz: [...]`, `translations: {es:{title,steps:[{n,title,instruction}]}, tl:{…}}`   |
| `attempts`   | `_id`, `caregiver_id`, `skill_id`, `clip_id`, `checks: [{id,result,time,seen}]`, `overall`, `created_at`                                                                                                   |
| `signoffs`   | `_id`, `attempt_id`, `caregiver_id`, `skill_id`, `signer`, `decision`, `note`, `at`                                                                                                                         |
| `questions`  | `_id`, `caregiver_id`, `text`, `language` (`'en'`\|`'es'`\|`'tl'`), `status` (`'answered'`\|`'waiting_owner'`), `answer: str|null`, `card_id: str|null`, `source` (`'ai'`\|`'card'`\|`'owner'`), `created_at`, `answered_at: str|null` (shipped on `channel/questions`) |
| `cards`      | `_id`, `role` (`'caregiver'`), `question`, `answer`, `created_at` (shipped on `channel/questions`) |
| `policies`   | `_id`, `title`, `text`. Seeded idempotently at channel feature startup (`"Client refuses care"`, `"Client falls"`, `"Running late to a shift"` — developer placeholders). |
| `conversations` | `_id`, `caregiver_id`, `channel` (`"web"`; `"whatsapp"` reserved), `state` (`idle|in_lesson|quiz|awaiting_video|awaiting_result`), `skill_id: str|null`, `step_index: int`, `quiz_index: int`, `correct_count: int`, `pending_attempt_id: str|null`, `greeted: bool`, `updated_at` (shipped on `channel/questions`) |
| `messages`   | `_id`, `caregiver_id`, `direction` (`'in'`\|`'out'`), `channel` (`"web"`), `text`, `media_id: str|null`, `created_at` (shipped on `channel/questions`) |
| `lesson_jobs` | `_id`, `status` (`converting|analyzing|extracting_frames|ready|publishing|published|failed`), `video_id`, `source_credit`, `skill_id: str|null`, `duration_s`, `draft` (shape per CONTRACTS §1c), `problems[]`, `draft_rev: int`, `created_at`, `updated_at`, heartbeat fields (shipped on `lessons/record`; owned by that feature). Published rows are wiped on publish — see §1c. |
| `incidents`  | Reserved for later phases.                                                                                                                                                                                  |
| `plans`      | Reserved for later phases.                                                                                                                                                                                  |

## 7. Seed

`backend/seed/seed.py` is **idempotent**. On run (or auto-run at
startup when the `agencies` collection is empty), it wipes only the
collections it owns (`agencies`, `caregivers`, `clients`, `skills`,
`attempts`, `signoffs`) and re-inserts. `questions`, `cards`,
`incidents`, `plans` are left untouched.

Run manually: `python -m backend.seed.seed` from the repo root.

Reference frames for every skill step and clips for every attempt go
through `MediaStore.save()` so GridFS populates alongside documents.

## 8. Design tokens

Warm palette. All values live in `src/App.css` under `:root` and
`[data-side="caregiver"]`.

| token              | agency        | caregiver     | role                       |
| ------------------ | ------------- | ------------- | -------------------------- |
| `--fs-bg`          | `#fdf8f1`     | `#2a1f17`     | shell background           |
| `--fs-fg`          | `#1c1611`     | `#fdf5e7`     | body text                  |
| `--fs-muted`       | `#786b60`     | `#c9b89f`     | secondary text             |
| `--fs-border`      | `#e9d9c6`     | `#4a382a`     | dividers / outlines        |
| `--fs-surface`     | `#ffffff`     | `#35281e`     | cards & nav background     |
| `--fs-accent`      | `#fcefd9`     | `#4a382a`     | chip background            |
| `--fs-primary`     | `#b4511b`     | `#e78a3c`     | active nav / CTA           |
| `--fs-primary-fg`  | `#ffffff`     | `#1c1611`     | text on primary            |
| `--fs-tap`         | `44px`        | `44px`        | minimum tap target         |
| `--fs-max-w`       | `480px`       | `480px`       | phone-cap on desktop       |
| `--fs-radius`      | `14px`        | `14px`        | card radius                |

Fonts: `Fraunces` (serif, headings/body) + `Public Sans` (sans,
numbers/forms). Both pulled from Google Fonts in `public/index.html`.

Base font 16 px, min tap target 44 px, mobile frame capped at 480 px on
desktop (responsive down to 320 px).

## 9. Boot / env

- `MONGO_URL` — required.
- `DB_NAME` — defaults to `firstshift`.
- `GEMINI_API_KEY` — required for `/api/ai/health`; missing → 503.
- `GEMINI_MODEL` — optional, defaults to `gemini-3.5-flash`.
- `CORS_ORIGINS` — comma-separated, defaults to `*`.

OpenAPI at **`/api/openapi.json`**. Interactive docs: `/api/docs`,
`/api/redoc`.

## 10. TODOs for later phases

- Signed, short-lived media access tokens (via the `url` field — not
  the raw UUID path).
- Real auth. Role switch and `/c/{code}` are **not** real auth today —
  they're convenient entry points for Phase 2 UI. The Batch-3
  `X-Firstshift-Role` header is a **client-declared** role (see
  `backend/roles.py`); a motivated user can forge it by typing one
  header. Everything the header protects — signoff, question answers,
  skill writes — must be re-protected by real identity once auth lands.
- Wire each service stub to `call_gemini` **on its own fork branch** —
  stubs stay fake on `main` so forks remain independent.
- `questions`, `cards`, `incidents`, `plans` collection shapes.
- **Pro-translator review** of `translations.es` / `translations.tl`
  placeholder strings in `backend/seed/seed.py` *and* in
  `backend/features/grading/seed.py` (Glove removal).
- **WhatsApp integration deferred** per user instruction. The
  `conversations.channel` and `messages.channel` fields are preserved
  at `"web"` for forward-compat. No Twilio code exists today.
- **`backend/scripts/clean_test_residue.py`** — recommended but never
  written. Would purge tester-leftover `questions`, `lesson_jobs`,
  `uploads` rows + the GridFS blobs they reference. Current cleanup is
  manual (DB inspection + direct deletes). Priority: nice-to-have.
- **Grading auth**: `POST /api/grading/clips` and
  `POST /api/grading/attempts/{id}/signoff` are open today. Tie them
  to caregiver access-code / agency staff identity once real auth lands.
- **Clip retention**: the mp4 saved by `/api/grading/clips` has no
  expiry. Decide on a retention window (likely tied to signoff: keep
  until signoff + N days, then purge GridFS blob + attempt row's
  `clip_id`).
- **Frame cleanup**: `grade_clip_pipeline` uploads 2 fps JPEG frames
  (one per run) and keeps their UUIDs on the attempt in `frame_ids`.
  Nothing deletes them. Add a sweep job that deletes `frame_ids` blobs
  after `graded_at + 30 days` (same policy as clips, independently
  configurable).

## 11. Role × endpoint allow-sets (Batch-3 header gate)

> **Not real auth.** The frontend sends `X-Firstshift-Role` from
> `localStorage` and the backend trusts it. A motivated user can forge
> the header by typing one line into dev tools. This is a hide-and-
> disable UX plus a server-side 403 on destructive flows, not a
> security boundary. See §10 for the real-auth TODO.

Shipped on `mvp-hardening` as `backend/roles.py` + the response/request
interceptor pair in `frontend/src/api.js`. Full matrix:

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

### 403 detail shape (frontend parses `.allowed`)

```jsonc
// Header missing or empty
{ "detail": { "reason": "role_required",
              "allowed": ["Care Manager", "Trainer"] } }

// Header present but not in allow-set
{ "detail": { "reason": "role_not_allowed", "role": "Scheduler",
              "allowed": ["Care Manager", "Trainer"] } }
```

The frontend's response interceptor fires `onForbidden(payload)` on
either reason, surfacing a toast via `frontend/src/shell/Toasts.js`.
