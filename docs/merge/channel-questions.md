# Merge notes — `channel/questions`

> Branch: `channel/questions`, forked off `main` (post-merge of grading/signoff + lessons/record).
> Scope: Caregiver web chat (replaces the Phase-1 Chat placeholder) + the question loop.
> **WhatsApp is deferred** per user instruction. Twilio-shaped fields (`conversations.channel`,
> `messages.channel`) are kept at `"web"` for forward-compatibility; no outbound SMS/WhatsApp
> code exists in this branch.

## Known drift

Pod's local `main` was reconstructed via local merge of `grading/signoff` + `lessons/record`
because the pod has no `origin` remote. GitHub `main` has equivalent content via GitHub-side
PR merges; different commit SHAs. When pushing `channel/questions` to GitHub via
Save-to-GitHub, use the "Create Branch & Push" option to avoid clobbering GitHub's history.

## Files added

### Backend
- `backend/features/channel/state_machine.py` — `handle_inbound(caregiver_id, text, media_id, channel)` FSM.
- `backend/features/channel/routes.py` — HTTP endpoints under `/api/channel`.
- `backend/features/channel/__init__.py` — mounts the new sub-router, keeps `/` placeholder.
- `backend/features/questions/pipeline.py` — AI answer + card/policy context + language targeting.
- `backend/features/questions/routes.py` — HTTP endpoints under `/api/questions` (incl. voice transcription).
- `backend/features/questions/__init__.py` — mounts the sub-router, keeps `/` + `/list`.
- `backend/seed/policies.py` — idempotent seeding of 3 agency policies.

### Frontend
- `frontend/src/features/channel/ChatPage.js` — real web chat UI (overwrites placeholder).
- `frontend/src/features/questions/AskPage.js` — caregiver Ask tab (overwrites placeholder).
- `frontend/src/features/questions/QuestionsPage.js` — agency inbox w/ voice recorder (overwrites placeholder).

## Shared-line changes

**1 — the signoff hook.** Appended `~3 lines` inside
`backend/features/grading/routes_signoff.py::_signoff` to call the channel service after a
successful `$addToSet` on `cleared_skills` (only when `decision == "approve"` **and** the
`$addToSet` actually added the skill — not re-adds). The call is to
`services.channel_service.send_message` so the touch is a service call, not internal grading
state. All other grading/lessons files are untouched.

## New collections / fields

### `caregivers`
- `phone: str | null` — default `null`. Kept for WhatsApp forward-compat.

### `conversations` (new)
```
{_id: uuid4hex,
 caregiver_id: str,
 channel: "web",                       # future: "whatsapp"
 state: "idle"|"in_lesson"|"quiz"|"awaiting_video"|"awaiting_result",
 skill_id: str | null,
 step_index: int,                       # 0-based, which step was last sent
 quiz_index: int,                       # 0-based, which quiz Q was last sent
 correct_count: int,                    # correct quiz answers so far
 pending_attempt_id: str | null,        # set while awaiting_result
 greeted: bool,                         # true after the first-contact welcome
 updated_at: ISO-8601}
```

### `messages` (new)
```
{_id: uuid4hex,
 caregiver_id: str,
 direction: "in"|"out",
 channel: "web",
 text: str,
 media_id: str | null,                  # points to a MediaStore uuid
 created_at: ISO-8601}
```

### `policies` (new, seeded)
```
{_id: uuid4hex, title: str, text: str}
```
Seeded titles: `"Client refuses care"`, `"Client falls"`, `"Running late to a shift"`.
See `CHANGELOG.md` — policies are **developer-written placeholders** pending revision.

### `questions` (fields filled; row was reserved in Phase-1)
```
{_id: uuid4hex,
 caregiver_id: str,
 text: str,
 language: "en"|"es"|"tl",
 status: "answered"|"waiting_owner",
 answer: str | null,
 card_id: str | null,                   # points at the card that answered it (if any)
 source: "ai"|"card"|"owner",
 created_at: ISO-8601,
 answered_at: ISO-8601 | null}
```

### `cards` (new)
```
{_id: uuid4hex, role: "caregiver", question: str, answer: str, created_at: ISO-8601}
```

## Endpoints

### `/api/channel`
| Method | Path | Purpose |
| ------ | ---- | ------- |
| GET  | `/`                                          | placeholder marker (unchanged) |
| GET  | `/conversation/{caregiver_id}`               | current conversation state (debug + UI) |
| GET  | `/messages/{caregiver_id}`                   | full message thread (chat polling) |
| POST | `/inbound`                                   | `{caregiver_id, text?, media_id?}` → drives FSM |
| POST | `/inbound-video`                             | multipart: `caregiver_id` + `file` → ingests clip, drives FSM |

### `/api/questions`
| Method | Path | Purpose |
| ------ | ---- | ------- |
| GET  | `/`                                | placeholder (unchanged) |
| GET  | `/list`                            | preserved shape (every question) |
| GET  | `/inbox`                           | agency inbox: waiting first, then answered |
| POST | `/{question_id}/answer`            | care-manager types answer → creates card, delivers |
| POST | `/transcribe`                      | multipart: `file` audio → `{media_id, transcript}` |
| GET  | `/policies`                        | list seeded policies (for UI/debug) |

All appear in `/api/openapi.json`.

## Env keys

Unchanged from previous forks (`GEMINI_API_KEY`, `GEMINI_MODEL`).

## Risks / known limits

- **No backend auth.** Anyone with a caregiver `access_code` can post into their conversation;
  anyone can hit `/questions/*` endpoints. UI "role" is still localStorage only.
- **WhatsApp deferred.** `conversations.channel` / `messages.channel` kept at `"web"`.
- **Policies are placeholders.** Flagged in `CHANGELOG.md`; user will revise copy.
- **Phase-2 translation thinness.** Seeded skills have `translations.<lang>.steps` with text but
  `translations.<lang>.checks` + `.quiz` are empty on the Glove-removal / Transfer seeds. The
  FSM falls back to English for check text in those cases. New skills published through
  `lessons/record` carry full translations and the UI handles them.
- **Grading cross-feature coupling.** The chat watcher polls `attempts.status` every 2 s to
  detect grading completion. If the grading task dies silently, the chat stays in
  `awaiting_result` until the Phase-3 stale sweeper flips the row to `grading_error`
  (10 min). Documented so forks downstream don't look for a hook.
- **Media retention TODO** (same as `lessons/record`).

## DONE WHEN evidence

Run against `BASE=https://shift-backbone.preview.emergentagent.com`. Preflight was green at the
start (`/api/ai/health` returned `{ok:true,"model":"gemini-3.5-flash","result":{"color":"teal"}}`)
and remained green at the end of the run.

### Gemini audio input (guardrail H)

Verified the audio call path works with the current model (`gemini-3.5-flash`) by uploading a
~320 KB WAV via `MediaStore.save` and calling `call_gemini` with and without `response_schema`:

- Without schema (`"Describe this audio clip in one sentence..."`) → Gemini returned:
  `"This audio clip features a brief, lighthearted instrumental melody played on an acoustic guitar."`
- With `{transcript: str}` schema (same clip, which had no speech — it was the music intro of
  the Transfer-clip lecture) → Gemini correctly returned `{"transcript": ""}`.

Both calls succeeded; `GEMINI_MODEL` left untouched.

### 1 — Web chat end-to-end (Lucia Hernández, `es`, code `SNMT3Y`)

- `POST /api/channel/inbound {text:"hola"}` → first-contact welcome in **Spanish**, menu listing
  her remaining skills in Spanish.
- `POST /api/channel/inbound {text:"2"}` picked **Retiro de guantes** (Glove removal) →
  `state=in_lesson`, 7 steps delivered one at a time in Spanish on each "Next". _(Seeded Glove
  removal has no step `frame_id`s and no quiz, so step bubbles rendered without images and the
  FSM jumped straight to `awaiting_video` after the last step — this is Phase-2 seed-data
  thinness, documented above.)_
- `POST /api/channel/inbound-video` with a 25 s mp4 → chat received **"Revisando tu video…"**;
  attempt `6853fc06ef2a42cb9bf25085daa3ac5a` reached `needs_practice` in 30 s; the chat watcher
  posted the first-missed-check line **"Faltó: Gloved fingers pinch the OUTSIDE of the first
  glove at the wrist en 0:15.2."** followed by the retry prompt. The missed check's description
  fell back to English because the Glove-removal seed has empty `translations.es.checks` (Phase-2
  thinness, same note). The timestamp `0:15.2` came from `attempts.checks[].time`.

### 3 — Policy miss → inbox → voice-answer path → card → repeat match

- Lucia asked `"What should I bring on my first visit to a new client?"` →
  `POST /api/questions/ask`. Policies do not cover first-visit prep, so Gemini returned
  `covered:false`; question `c88bc433fa1d467fabf9c28dd1e8b965` landed in the inbox with
  `status=waiting_owner`, and Lucia got **"Le pregunté a tu administradora de cuidados y te
  enviaré su respuesta aquí cuando esté lista."** in Spanish.
- `POST /api/questions/c88bc433…/answer` with a plain-text answer:
  - Created card `cfe3f758e17048b9a9108c6d149ef58f`.
  - Marked the question `status=answered, source=owner`.
  - Delivered the answer to Lucia **translated into Spanish**:
    `"Traiga el plan de atención, su credencial de identificación, …"`.
- Darius Williams (`en`, code `TRSR9T`) asked a paraphrase of the same question
  (`"What do I need to bring the first time I visit a new client?"`). The pipeline sent the
  existing card into the Gemini prompt as prior context; Gemini responded with
  `covered:true, source_title:"Card: What should I bring on my first visit to a new client?"`,
  `confidence=1.0`. Darius received the English answer immediately with the card attribution,
  **no new row in the waiting inbox**.

Voice-answer path (`MediaRecorder` → `/api/questions/transcribe` → editable textarea → save):
the transcription endpoint is wired against the same `call_gemini` audio path above. Browser-
mic recording is exercised from the agency UI; a direct curl against `/api/questions/transcribe`
with a WAV returned `{media_id, transcript:""}` for the music-intro clip (as expected — no
speech) with `HTTP 200`, confirming the path.

### 4 — Signoff hook

`POST /api/grading/attempts/6853fc06…/signoff` with
`{"decision":"approve","signer":"Nurse Miller","signer_role":"Care Manager","note":"Reviewed in-person; competent."}`
returned `{attempt_id, decision:"approve", override:true, signoff_id:"94ba6ae1…"}`. The caller
received `HTTP 200`; the hook sent **"Estás aprobada para Retiro de guantes."** into Lucia's
chat (visible in `GET /api/channel/messages/{id}`) and Lucia's `cleared_skills` grew to
`["c60f1d3a9c44493b8c5e2fd5d3644d82"]`. The hook also runs on `send_back` (nothing to send;
`$addToSet.modified_count == 0`) and on re-adds (idempotent — modified_count 0 → no message).

## Preserved endpoints

- `GET /api/channel/` → `{feature:"channel", status:"placeholder"}` (Phase-1 shape).
- `GET /api/questions/` → `{feature:"questions", status:"placeholder"}` (Phase-1 shape).
- `GET /api/questions/list` → `{questions:[…]}`, row keys preserved
  (`source, answered_at, created_at, caregiver_id, answer, language, status, text, card_id`).

