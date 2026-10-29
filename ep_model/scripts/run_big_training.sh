#!/usr/bin/env bash
# Phase A (resume, capped) → Phase B (safe_run, parallel engines) → Phase C (train + evaluate).
# Repo root = ChessCoach. Logs: ep_model/processed/phase_a_big.log, safe_run_big.log
# WORKERS=8 by default (one single-threaded Stockfish each, ~330 MB RAM per engine).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
# shellcheck source=/dev/null
source .venv/bin/activate

echo "=== Phase A: up to 100000 new games, resume, shard-rows 50000 ==="
python -m ep_model.sampling.generate_rows \
  --resume \
  --shard-rows 50000 \
  --max-games 100000 \
  -v 2>&1 | tee ep_model/processed/phase_a_big.log

WORKERS="${WORKERS:-8}"
echo "=== Phase B: safe_run (${WORKERS} workers, 48h wall, 130 GiB processed cap, 15 GiB free min) ==="
python -m ep_model.scripts.safe_run \
  --policy ep_model/config/engine_policy_parallel.json \
  --workers "$WORKERS" \
  --max-wall-hours 48 \
  --max-processed-gib 130 \
  --min-free-gib 15 \
  -v 2>&1 | tee ep_model/processed/safe_run_big.log

echo "=== Phase C: train on all Phase B shards + evaluate vs baselines ==="
python -m ep_model.training.train --sharded-load -v
python -m ep_model.training.evaluate -v

echo "=== Done: $(date -u) — see ep_model/models/ep_eval_report.md ==="
