# FirstShift — Product Requirements (living doc)

## Original problem statement

Phase 1 of FirstShift, a phone-first web app for a home-care agency.
Teammates will fork this repo and extend features in parallel, so
**structure and fork-safety matter more than features** in this build.

Stack: React (CRA) + FastAPI + MongoDB. User-facing AI integration is
Gemini via the `google-genai` SDK.

## User personas (Phase 2+)

- **Agency ops / admin** — manages caregivers, clients, skills,
  reviews grading output, signs off attempts.
- **Caregiver** — accesses the app via a 6-char access code, consumes
  lessons, submits video clips for grading, asks questions, receives
  remediation plans.

## Core (static) requirements

- Phone-first UX (16 px base, 44 px tap target).
- Fork-safe code structure — **no shared registry files**.
  - Backend: `features/<name>/__init__.py` exposing `router`;
    auto-mounted at `/api/<name>`.
  - Frontend: `features/<name>/routes.js` exporting `{routes, nav}`;
    discovered via `require.context`.
- Single GridFS-backed media interface (`MediaStore`), 50 MB cap,
  content-type allowlist, publicly readable URLs (Twilio needs them).
- Gemini helper with File API support for large videos and structured
  JSON output via `response_schema`.
- MongoDB collections pre-created with the one Phase-1 index
  (`caregivers.access_code` unique sparse).

## What's shipped (grows over time)

### 2026-02-24 — Phase 1: Backbone
- Backend feature auto-discovery (ops, lessons, grading, questions,
  channel placeholders).
- Frontend feature auto-discovery via `require.context`.
- Service stubs (`grade_clip`, `build_lesson`, `send_message`,
  `answer_question`, `build_plan`) with documented shapes.
- GridFS `MediaStore` + `POST /api/media` + `GET /api/media/{uuid}`.
- `google-genai` Gemini helper + `GET /api/ai/health` (verified
  returning real `{ "color": "teal" }` from a generated test PNG).
- Mongo collections + unique index.
- Phone-first base styles.
- `docs/CONTRACTS.md` and `docs/CHANGELOG.md`.
- Committed to `main` as **"Phase 1: backbone — auto-discovery,
  GridFS media, Gemini helper, stubs, contracts"**.

## Prioritized backlog

### P0 (Phase 2)
- Real app shell (agency vs. caregiver side-nav, role switch stub,
  `/c/{code}` caregiver entry).
- Seed data: one agency, a handful of caregivers (with real access
  codes), a client, a few skills with steps / checks / quizzes.
- Nav manifests populated in each feature's `routes.js`.
- Caregiver access-code login (still not real auth — scoped lookup).

### P1 (Phase 3+)
- Swap each service stub body to call `call_gemini` with the right
  prompt + `response_schema`.
- Attempt submission flow (upload clip → `grade_clip` → persist to
  `attempts` → agency `signoff`).
- Lessons authoring (upload reference video → `build_lesson`).
- Caregiver Q&A UI (`answer_question`).
- Outbound messaging (`send_message` → Twilio/WhatsApp).
- Remediation plans (`build_plan`).

### P2 (later)
- Real auth (JWT + role claims), signed media URLs.
- Internationalisation (`en` / `es` / `tl`) end-to-end.
- Analytics dashboards, incident reporting, audit log.

## Next tasks

Awaiting Phase 2 brief from user.
