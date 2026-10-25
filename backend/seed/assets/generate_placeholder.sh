#!/usr/bin/env bash
# Regenerate the seed placeholder clip. Run from the repo root.
#
# Produces a 2-second, 320x240, H.264 + AAC mp4 (~3 KB) that plays in
# Chrome, Safari (mobile + desktop) and Firefox. Used by seed.py for
# `attempts.clip_id`.
set -euo pipefail
OUT="$(cd "$(dirname "$0")" && pwd)/placeholder.mp4"
ffmpeg -y -v error \
  -f lavfi -i "color=c=black:s=320x240:d=2:r=15" \
  -f lavfi -i "anullsrc=r=8000:cl=mono" \
  -shortest \
  -c:v libx264 -pix_fmt yuv420p -preset veryfast -crf 32 \
  -c:a aac -b:a 24k \
  -movflags +faststart \
  "$OUT"
ls -lh "$OUT"
