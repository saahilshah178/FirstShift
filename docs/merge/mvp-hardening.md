# Merge notes — `mvp-hardening`

> Branch: `mvp-hardening`, forked off `main` (post local-merge of `channel/questions`).
> Scope: MVP hardening — media, data integrity, grading reconciliation, role gating, UX polish.
> Ops/Today/Clients/New-hires deferred to a later fork.

## Hard decisions baked in

- **Duplicate skills**: hard-deleted the losers, migrated attempts/signoffs/cleared_skills/
  lesson_jobs/clients.required_skills refs to the winner (see **Dedup** below).
- **Quiz count**: no min/max — publish allowed with any `N` quiz questions, incl. 0.
- **Role matrix**:
  - **Care Manager** — unchanged, full access.
  - **Trainer** — no signoff, no card creation on `/questions/{id}/answer`,
    no policy writes, no skill archive.
  - **Scheduler** — view-only on skills (list + detail only); 403 on upload/edit/publish/
    archive/translation edit.
  - Backend is source of truth; frontend sends `X-Firstshift-Role` with every agency
    request and hides UI the role can't act on. **TODO: real auth replaces this.**

## Files added (so far)

### Backend
- `backend/scripts/__init__.py`
- `backend/scripts/faststart_backfill.py`     — one-shot GridFS re-encode with `+faststart`.
- `backend/scripts/dedupe_skills.py`          — hard-delete loser skills + migrate refs.

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
