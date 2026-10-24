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
| `GET /api/questions/list`                  | `{questions:[]}` — reserved for later phases.                    |
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

All ten collections are created at startup. Only index:
`caregivers.access_code` **unique sparse**.

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
| `questions`  | Reserved for later phases.                                                                                                                                                                                  |
| `cards`      | Reserved for later phases.                                                                                                                                                                                  |
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

- Signed media access tokens (via the `url` field — not the raw UUID
  path).
- Real auth. Role switch and `/c/{code}` are **not** real auth today —
  they're convenient entry points for Phase 2 UI.
- Wire each service stub to `call_gemini`. Signatures are frozen.
- `questions`, `cards`, `incidents`, `plans` collection shapes.
- Pro-translator review of the `translations.es` / `translations.tl`
  placeholder strings in `backend/seed/seed.py`.
