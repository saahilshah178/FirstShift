# FirstShift — Changelog

## Phase 1 — Backbone (2026-02-24)

Shipped the fork-safe scaffolding other branches will build on.

- **Backend auto-discovery.** `backend/features/*` subpackages are
  discovered and mounted at `/api/<name>` by `backend/server.py` at
  startup. Import failures are logged and skipped (fail-open).
- **Frontend auto-discovery.** `src/featureRegistry.js` uses
  `require.context` (webpack built-in via CRA) to pick up every
  `src/features/*/routes.js`. No shared `routes.js` to edit.
- **Feature stubs.** `ops`, `lessons`, `grading`, `questions`,
  `channel` each ship a placeholder backend router (`GET /` →
  `{"feature": "<name>", "status": "placeholder"}`) and a placeholder
  frontend page/route. All nav manifests are empty for now.
- **Service stubs** in `backend/services/` (`grade_clip`,
  `build_lesson`, `send_message`, `answer_question`, `build_plan`)
  return realistic shapes with `"model": "stub"`. Teammate branches
  swap the body, not the signature.
- **GridFS media store.** `MediaStore.save()` / `.get()` on
  `AsyncIOMotorGridFSBucket`. `POST /api/media` (multipart) and
  `GET /api/media/{uuid}` with the content-type allowlist, 50 MB cap,
  413 on overflow, 415 on bad types, 404 on missing.
- **Gemini helper wired for real.** `backend/ai/gemini.py::call_gemini`
  uses `google-genai` (new SDK). Images and small media go inline;
  videos >20 MB are uploaded via the File API and polled until
  `ACTIVE`. Supports structured output via `response_schema`.
  `GET /api/ai/health` round-trips a tiny PNG → Gemini and verifies
  the returned structured JSON. Returns 503 on failure.
- **MongoDB collections.** `agencies`, `caregivers`, `clients`,
  `skills`, `attempts`, `signoffs`, `questions`, `cards`, `incidents`,
  `plans` created empty. Unique sparse index on
  `caregivers.access_code`.
- **Phone-first frontend base.** 16 px body, 44 px tap-target CSS
  variable, iOS viewport meta. No real app shell yet — the home page
  just enumerates the auto-discovered feature routes to prove the
  wiring.
- **Docs.** `docs/CONTRACTS.md` documents every seam branches depend
  on. `/api/openapi.json` is exposed for the tester.

### Known non-blockers

- `/api/ai/health` can intermittently return 503 UNAVAILABLE when the
  underlying Gemini model is overloaded. This is spec-compliant
  behavior (the endpoint surfaces the real error) and resolves
  automatically on retry.
