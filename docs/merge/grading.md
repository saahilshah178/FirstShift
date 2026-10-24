# Merge notes — `grading/signoff`

> **Working document.** Filled in across the seven staged commits in
> this branch; finalised in the last `docs(grading)` commit.

## Branch

- `grading/signoff` off `main` at `6f18729`.

## System dependencies

- **ffmpeg + ffprobe** are required for clip transcoding and frame
  extraction. Installed on the preview container with:
  ```bash
  apt-get update && apt-get install -y ffmpeg
  ```
  Verified: `ffmpeg 5.1.9`, `ffprobe 5.1.9`.
- Production builds must install `ffmpeg` in the base image (Dockerfile
  or buildpack). If missing at runtime, `POST /api/grading/clips`
  returns `415` on the first invocation (ffprobe fails to decode).

## Env

- `GEMINI_API_KEY` — unchanged, required.
- `GEMINI_MODEL` — already env-driven in `backend/ai/gemini.py` from
  Phase 1 (default `gemini-3.5-flash`). This branch adds the key
  explicitly to `backend/.env` so operators see it; the default value
  is unchanged.

## Shared-line changes

_(Expected: 0. Filled in by later commits.)_

## Files added

_(Filled in by later commits.)_

## New endpoints

_(Filled in by later commits.)_

## New fields and defaults

_(Filled in by later commits.)_

## TODOs raised in `docs/CONTRACTS.md`

_(Filled in by later commits.)_

## Manual test plan

_(Filled in by the final commit.)_
