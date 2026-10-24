# FirstShift — Contracts (Phase 1)

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

Current Phase 1 features (each only returns a placeholder):
`ops`, `lessons`, `grading`, `questions`, `channel`.

## 2. Frontend auto-discovery (features)

`src/featureRegistry.js` uses `require.context('./features', true, /\/routes\.js$/)`
(CRA/webpack built-in) to find every `src/features/<name>/routes.js`.
No central file lists feature names — fork-safe.

**A feature's `routes.js` must export:**

```js
export const routes = [
  { path: "/<name>", element: <SomeComponent /> },
  // additional routes allowed
];

export const nav = [
  // Phase 2+ will populate this. In Phase 1 it is [].
  // { label: "Ops", path: "/ops", order: 10, side: "agency" }
];
```

- `side` is `"agency" | "caregiver"`.
- `order` is a number; nav is sorted ascending.
- Broken `routes.js` files are logged and skipped (fail-open).

## 3. Service stubs (`backend/services/`)

Each stub returns realistic *fake* data today. Teammate branches will
later swap each body to call `backend/ai/gemini.py::call_gemini`.

### `grade_clip(skill_id: str, caregiver_id: str, clip_id: str) -> dict`
```jsonc
{
  "skill_id": "...", "caregiver_id": "...", "clip_id": "...",
  "checks": [
    { "id": "c1", "description": "...",
      "result": "pass"|"fail"|"unclear",
      "time": 3.2, "seen": true, "safety_critical": true }
  ],
  "overall": "pass"|"fail"|"needs_review",
  "score": 0.0..1.0,
  "created_at": "ISO-8601",
  "model": "stub"
}
```

### `build_lesson(video_id: str) -> dict`
```jsonc
{
  "video_id": "...", "title": "...",
  "steps":  [{ "n": 1, "title": "...", "instruction": "...",
               "start": 0.0, "end": 4.0, "frame_id": null }],
  "checks": [{ "id": "...", "description": "...",
               "safety_critical": true }],
  "quiz":   [{ "id": "...", "prompt": "...",
               "choices": ["..."], "answer_index": 0 }],
  "translations": { "es": { "title": "..." }, "tl": { "title": "..." } },
  "model": "stub"
}
```

### `send_message(caregiver_id: str, text: str, media_url: str | None = None) -> dict`
```jsonc
{
  "message_id": "uuid4-hex", "caregiver_id": "...",
  "text": "...", "media_url": null,
  "status": "queued"|"sent"|"failed",
  "provider": "stub",
  "sent_at": "ISO-8601"
}
```

### `answer_question(caregiver_id: str, text: str) -> dict`
```jsonc
{
  "question_id": "uuid4-hex", "caregiver_id": "...",
  "question": "...", "answer": "...",
  "citations": [{ "skill_id": "...", "step_n": 1, "snippet": "..." }],
  "confidence": 0.0..1.0,
  "answered_at": "ISO-8601",
  "model": "stub"
}
```

### `build_plan(caregiver_id: str, note_text: str) -> dict`
```jsonc
{
  "plan_id": "uuid4-hex", "caregiver_id": "...", "note": "...",
  "items": [{ "skill_id": "...",
              "action": "review"|"reattempt"|"shadow",
              "due_in_days": 2, "reason": "..." }],
  "created_at": "ISO-8601",
  "model": "stub"
}
```

## 4. `MediaStore` (`backend/media/store.py`)

GridFS-backed, single interface:

```python
class MediaStore:
    async def save(self, file_bytes: bytes, content_type: str,
                   filename: str | None = None) -> str
    async def get(self, uuid_str: str) -> tuple[AsyncIterator[bytes], str, str]
```

- UUIDs are opaque (`uuid4().hex`); callers must not inspect them.
- `get()` raises `FileNotFoundError` on unknown UUIDs; HTTP layer maps
  that to 404.
- `AsyncIOMotorGridFSBucket` with `bucket_name="media"` on
  `db[DB_NAME]`.

### HTTP

- `POST /api/media` — multipart form, field `file`.
  - Allowed content types: `video/mp4`, `video/quicktime`, `video/webm`,
    `audio/mpeg`, `audio/wav`, `audio/webm`, `image/jpeg`, `image/png`,
    `image/webp`.
  - Max size: **50 MB**. Over → `413`.
  - Bad content type → `415`.
  - Returns `{ "uuid": "...", "url": "/api/media/<uuid>", "content_type": "...", "size": N }`.
- `GET /api/media/{uuid}` — streams the blob with its real content type;
  publicly readable (Twilio and similar providers will need it).
  Missing → `404`.

> **TODO (later phase):** media access will require signed tokens, not
> raw UUIDs. Keep callers using the returned `url` field so we can swap
> in token-based paths without churn.

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
- For video blobs **> 20 MB**, uploads via the `google-genai` File API,
  polls `files.get()` until `state == ACTIVE` (timeout ~60 s), then
  references the uploaded file. Otherwise sends bytes inline.
- `response_schema` → structured JSON output. Returns the parsed dict.
- Without `response_schema` → returns `{"text": "<raw response>"}`.
- Key: `GEMINI_API_KEY` env var. Missing → `/api/ai/health` returns 503
  with `{"ok": false, "error": "GEMINI_API_KEY is not set"}`.
- Model default: `gemini-3.5-flash` (override via `GEMINI_MODEL` env var).

### Health

- `GET /api/ai/health` — generates a tiny solid-color PNG, saves it via
  `MediaStore`, then calls `call_gemini` with
  `response_schema={"type":"object","properties":{"color":{"type":"string"}},"required":["color"]}`.
  Returns `{"ok": true, "model": "...", "result": {"color": "..."}}` on
  success, `503 {"ok": false, "error": "..."}` on failure.

## 6. MongoDB collections (Phase 1 shapes)

All ten collections are created at startup (empty). Only index:
`caregivers.access_code` **unique sparse**.

| Collection   | Fields                                                                                                                                                                                                                              |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `agencies`   | `_id`, `name`, `created_at`                                                                                                                                                                                                         |
| `caregivers` | `_id`, `agency_id`, `name`, `language` (`'en'`\|`'es'`\|`'tl'`), `hired_at`, `experience_note`, `cleared_skills: [skill_id]`, `access_code: str` (6 chars, `[A-HJ-KM-NP-Z2-9]`, unique), `created_at`                                |
| `clients`    | `_id`, `agency_id`, `name`, `required_skills: [skill_id]`                                                                                                                                                                           |
| `skills`     | `_id`, `title`, `steps: [{n, title, instruction, start, end, frame_id}]`, `checks: [{id, description, safety_critical: bool}]`, `quiz: [...]`, `translations: {es: {...}, tl: {...}}`                                                |
| `attempts`   | `_id`, `caregiver_id`, `skill_id`, `clip_id`, `checks: [{id, result, time, seen}]`, `overall`, `created_at`                                                                                                                         |
| `signoffs`   | `_id`, `attempt_id`, `caregiver_id`, `skill_id`, `signer`, `decision`, `note`, `at`                                                                                                                                                 |
| `questions`  | Reserved for later phases.                                                                                                                                                                                                          |
| `cards`      | Reserved for later phases.                                                                                                                                                                                                          |
| `incidents`  | Reserved for later phases.                                                                                                                                                                                                          |
| `plans`      | Reserved for later phases.                                                                                                                                                                                                          |

## 7. Boot / env

- `MONGO_URL` — required.
- `DB_NAME` — defaults to `firstshift` (template ships `test_database`;
  override in `backend/.env` if desired).
- `GEMINI_API_KEY` — required for `/api/ai/health`; missing → 503.
- `GEMINI_MODEL` — optional, defaults to `gemini-3.5-flash`.
- `CORS_ORIGINS` — comma-separated, defaults to `*`.

OpenAPI exposed at **`/api/openapi.json`**. Interactive docs at
`/api/docs` and `/api/redoc`.

## 8. TODOs for later phases

- Media access will require signed tokens; the `url` field returned by
  `POST /api/media` is the stable integration point — do not hard-code
  `/api/media/<uuid>` paths in the frontend.
- Role-switch and `/c/{code}` are **not** real auth — real auth lands
  in Phase 2+.
- `questions`, `cards`, `incidents`, `plans` collection shapes are
  reserved; owner branches define them when they ship.
- Service stubs still return fake data — swap their bodies to call
  `call_gemini` without changing their signatures.
