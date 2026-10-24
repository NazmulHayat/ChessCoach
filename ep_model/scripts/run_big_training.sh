#!/usr/bin/env bash
# Phase A (resume, capped) → Phase B (safe_run). Repo root = ChessCoach.
# Logs: ep_model/processed/phase_a_big.log, safe_run_big.log
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
# shellcheck source=/dev/null
source .venv/bin/activate

echo "=== Phase A: up to 100000 new games, resume, shard-rows 50000 ==="
python -m ep_model.phase_a.generate_rows \
  --resume \
  --shard-rows 50000 \
  --max-games 100000 \
  -v 2>&1 | tee ep_model/processed/phase_a_big.log

echo "=== Phase B: safe_run (30h wall, 130 GiB processed cap, 15 GiB free min) ==="
python -m ep_model.scripts.safe_run \
  --max-wall-hours 30 \
  --max-processed-gib 130 \
  --min-free-gib 15 \
  -v 2>&1 | tee ep_model/processed/safe_run_big.log

echo "=== Done: $(date -u) ==="
