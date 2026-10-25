# Lichess Expected Points (EP) Model

Active training code for ChessCoach lives here. Legacy move-review and scripts are under `archive/` (see repo root `README.md`).

Minimal project structure for building an EP model from Lichess database exports.

**Pipeline and training design:** see [TRAINING_PLAN.md](TRAINING_PLAN.md) (extraction → engine → LightGBM).

## Folder structure

| Folder     | Purpose |
|------------|---------|
| `raw/`     | Raw Lichess `.pgn.zst` files (compressed PGN dumps). Do not modify. |
| `processed/` | Parquet shards, SQLite checkpoints, FEN eval cache. |
| `config/`  | `engine_policy.json` (default Phase B) + `engine_policy_background.json` (cooler / background). |
| `scripts/` | `safe_run` — batched Phase B with health checks, cooldowns, resume. |
| `phase_a/` | Row generation without engine. |
| `phase_b/` | Stockfish augmentation + FEN cache. |
| `phase_c/` | Train LightGBM EP model (split by `game_id`); evaluate vs eval-only baselines. |
| `phase_d/` | Inference (`EPModel`) + per-move PGN review with HTML report. |
| `models/`  | Saved `ep_lgbm.txt` + `ep_train_manifest.json` (gitignored except `.gitkeep`). |

## Setup

```bash
# From ChessCoach root
cd /Users/nazmulhayat/Desktop/Programming/ChessCoach

# Use one repo venv (from ChessCoach root)
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies (root requirements.txt includes EP stack)
pip install -r requirements.txt
# Or EP-only: pip install -r ep_model/requirements-ep.txt

# Link your Lichess dump into raw/ (from ChessCoach root)
ln -sf ../../lichess_db_standard_rated_2026-02.pgn.zst ep_model/raw/lichess_db_standard_rated_2026-02.pgn.zst
```

**Stockfish:** install the UCI binary and ensure `stockfish` is on your `PATH` (or edit `ep_model/config/engine_policy.json` → `stockfish_path`).

## Data source

- **Input**: `lichess_db_standard_rated_2026-02.pgn.zst` (Lichess monthly rated games, zstd-compressed)
- **Output**: Parquet tables in `processed/` for training and evaluation.

## Phase A — row generation (no engine)

Default **`--plies-per-game` is 5** (balance of coverage vs row count).

```bash
# Full run (example)
python -m ep_model.phase_a.generate_rows --shard-rows 50000

# Small pilot (adjust --max-games)
python -m ep_model.phase_a.generate_rows --max-games 2000 --resume -v
```

Useful flags:

- `--max-games` — cap games for a dry run or pilot.
- `--resume` — skip `game_id` values already recorded in `ep_model/processed/phase_a_checkpoint.sqlite`
- `--verbose` — debug logging

Without `--resume`, the Phase A checkpoint table is cleared at the start (Parquet shards are not deleted; remove old `rows_no_eval_part*.parquet` if you need a clean export).

## Phase B — Stockfish evals (pilot → scale-up)

Reads `processed/rows_no_eval_part*.parquet`, writes `processed/rows_with_eval_part*.parquet` with extra columns: `eval_cp_white`, `mate_white`, `eval_cp_stm`, `mate_stm`, `eval_depth`.

- **Policy:** `ep_model/config/engine_policy.json` (depth, threads, hash, `multipv` — use **1** for EP).
- **FEN cache:** `processed/fen_eval_cache.sqlite` — reused across runs (safe to keep).
- **Row checkpoint:** `processed/phase_b_row_checkpoint.sqlite` — `(game_id, ply)` already written; use **`--resume`** to continue after interrupt.

```bash
# Pilot: first N rows (tune N). Logs include rough “1M positions ≈ X CPU-hours” extrapolation.
python -m ep_model.phase_b.augment_evals --max-rows 3000 --flush-rows 1000 -v

# Resume after sleep / crash
python -m ep_model.phase_b.augment_evals --resume -v
```

**Fresh Phase B run** (no `--resume`): checkpoint DB is cleared. Delete old `rows_with_eval_part*.parquet` if you do not want leftover shards mixed with a new run.

**Estimating a full run:** use pilot `avg_engine_call` × expected **unique** FENs (cache helps repeats). Watch **disk** on `processed/`; delete Phase A-only Parquet after Phase B if you need space and no longer re-run Phase B from raw rows.

- **Machine-readable summary:** each successful run writes `processed/phase_b_last_summary.json` (`rows_written`, `no_pending_work`, `batch_limit_hit`, …). Use `--no-summary-json` to disable.
- **Background policy:** `config/engine_policy_background.json` uses lower `threads` / `hash_mb` than `engine_policy.json` (same depth) for less heat — point `--policy` at either file.

### Safe overnight / background Phase B (`safe_run`)

Runs Phase B in **batches** (`--batch-rows`, default 20k) with **cooldown** between batches, **Unix `nice`** (lower CPU priority for foreground work), and **automatic stops** if free disk, processed-folder size, swap, or wall-clock budget is exceeded. Progress is **one line per batch**; Stockfish stderr goes to `processed/safe_run_phase_b.log`. State: `processed/safe_run_state.json`. **Always resumable** via the same Phase B checkpoints as manual runs.

```bash
# Typical: ≤~130 GiB under ep_model/processed, ≥15 GiB free on /, ≤30 h wall, 2 min rest between batches
python -m ep_model.scripts.safe_run

# Tune budgets (example: ~100 GiB data cap, 30 h, optional row cap)
python -m ep_model.scripts.safe_run --max-processed-gib 120 --min-free-gib 18 --max-wall-hours 30 --max-total-new-rows 800000

# Print the Phase B command without running
python -m ep_model.scripts.safe_run --dry-run

# Fastest: 8 parallel single-threaded engines (~4x throughput on a 10-core laptop, ~330 MB RAM each)
python -m ep_model.scripts.safe_run --policy ep_model/config/engine_policy_parallel.json --workers 8
```

`--workers N` (also on `augment_evals`) runs N Stockfish processes, one per thread; rows, cache and output order are unchanged. Failed batches (e.g. macOS killing an engine under memory pressure) are retried up to `--max-retries` times; finished evals are in the FEN cache, so a retry loses little work. `scripts/run_big_training.sh` chains Phase A → parallel Phase B → train → evaluate.

Phase B already **streams** Parquet row groups in small chunks (no full-file RAM load). Phase C can load shards **one file at a time** with `--sharded-load` (see below).

## Phase C — train EP model (LightGBM)

Requires `rows_with_eval_part*.parquet` from Phase B.

- **Split:** by **`game_id`** (no row leakage across train/val).
- **Target:** `result_stm` (expected score in \([0,1]\), draw = 0.5), **cross-entropy** objective so predictions are calibrated probabilities.
- **Features:** `cp_stm_proxy` / `cp_white_proxy` (mate → pseudo-cp), Elos, ply, side, time fields, side-to-move-relative clocks (`clk_stm_sec`, `clk_opp_sec`, `clk_stm_frac`), categoricals `phase`, `time_class`, `rating_band`, `opening_eco`.
- **Clock dropout:** `--clock-dropout` (default 0.15) blanks clocks for that fraction of games so the model has a clock-unknown mode for PGNs without `[%clk]`.

```bash
python -m ep_model.phase_c.train -v
python -m ep_model.phase_c.train --max-rows 20000 --val-fraction 0.15
# Large Phase B output: lower peak RAM (reads one Parquet shard at a time; --max-rows ignored)
python -m ep_model.phase_c.train --sharded-load -v
```

**Outputs** (under `ep_model/models/`, local only — gitignored):

- `ep_lgbm.txt` — LightGBM model
- `ep_train_manifest.json` — features, metrics (log loss, MAE, RMSE, Brier), val metrics by `rating_band`, policy path
- `ep_val_game_ids.txt` — held-out games, used by the evaluation below

### Evaluate vs baselines

```bash
python -m ep_model.phase_c.evaluate -v
```

Scores the held-out games with the EP model and four baselines: constant, the Lichess win% curve, a logistic fit on eval only, and LightGBM on eval only. Writes `models/ep_eval_report.md` / `.json` (overall, by rating band and time class, a fixed-eval slice across player groups, calibration).

## Phase D — EP move review

```bash
python -m ep_model.phase_d.review game.pgn --html review.html
# PGN without Elo headers, faster engine pass:
python -m ep_model.phase_d.review game.pgn --white-elo 1450 --black-elo 1500 --depth 14
```

Per move: **EP if best** (mover's expected score had they played Stockfish's best move), **EP after** the move played, **EP loss**, and a label (excellent < 2%, good < 5%, inaccuracy < 10%, mistake < 15%, blunder ≥ 15%). Both EPs are scored on an opponent-to-move row with the same context, so side-to-move bias in the model cancels. The same thresholds on the Lichess curve give an eval-only label for comparison. Training used `engine_policy.json` depth; lower `--depth` is faster but slightly off-distribution.

In code: `EPModel().predict_rows(rows)` takes Phase B-shaped dicts and returns the side to move's expected score.
