# EP model: data extraction and training plan

This document describes how we go from the Lichess `.pgn.zst` dump to a trained **expected-points** model. Implementation: `ep_model/phase_a/generate_rows.py`, `ep_model/phase_b/augment_evals.py`, `ep_model/phase_c/train.py`, config in `ep_model/config/engine_policy.json`. For laptop-friendly batched Phase B (cooldowns, disk/swap guards, `nice`), use `ep_model/scripts/safe_run.py` and optionally `ep_model/config/engine_policy_background.json`.

## Goal

Learn a model **EP ≈ f(eval, ratings, context)** so review is anchored on objective eval but adjusted for human skill and game context.

- **Eval** comes from Stockfish at a fixed policy (depth or time), not from PGN.
- **Ratings / context** come from PGN headers + derived fields per row.
- **Label** is the game outcome, expressed from the relevant perspective (`result_white`, `result_stm`) for each sampled position (same game result for all plies in that game — standard for “from this position, how did the game end for this side”).

## Phase A — Row generation (no engine)

**Input:** Stream `ep_model/raw/*.pgn.zst` with `zstandard` + `chess.pgn.read_game` in a loop.

**Sampling (required for scale):**

- Stratify by **rating band** (e.g. WhiteElo / BlackElo buckets) and **time class** (from `TimeControl`).
- Per game, take **K random plies** (e.g. K=1–3) or every *m*-th ply, with optional caps by **ECO** prefix so one opening does not dominate.

**Per sampled half-move, emit:**

- Identity: `game_id` (from Site URL), `ply`, `move_number`, `side_to_move`, `fen` (define **before** `played_move_uci`), `played_move_uci`.
- Ratings: `white_elo`, `black_elo`, `elo_to_move`, `elo_opponent`, `elo_diff`.
- Time: `time_class`, `initial_time_sec`, `increment_sec` from `TimeControl`.
- Clocks: parse `[%clk ...]` when present; else null with a documented rule.
- Context: `phase` (heuristic: ply / material), `opening_eco` from game header (game-level).
- Outcomes: `result_white`, `result_stm` (0 / 0.5 / 1 from that side’s perspective).

**Output:** Parquet shards under `ep_model/processed/` (e.g. `rows_no_eval_partXXXX.parquet`), append-only, resumable (skip `game_id` already written if restarting from checkpoint).

## Phase B — Engine augmentation

**Input:** Rows with FEN (and metadata).

**For each row:**

- Run Stockfish once per FEN with a **fixed** policy: version, depth (or movetime), threads, hash documented in a small `ep_model/models/engine_policy.json` (or equivalent).
- Fill: `eval_cp_white`, `eval_cp_stm`, `mate_white`, `mate_stm`, `depth` (requested depth; store actual if you ever vary).

**Optimizations (same as discussed):**

- One long-lived engine process per worker; no subprocess per position.
- **FEN → eval** cache (disk or embedded DB) so reruns and duplicate FENs skip work.
- Parallel workers; each worker owns one engine.
- Optional: analyze only Phase A rows (already sampled).

**Output:** Parquet with full schema (e.g. `rows_with_eval_partXXXX.parquet`) or update in place by joining on `(game_id, ply)` — prefer immutable shards + manifest for reproducibility.

## Phase C — Training

**Split:** By **`game_id`** (never random rows from the same game in train and val) to avoid leakage.

**Features (v1):** `eval_cp_stm` (and/or `eval_cp_white`), `elo_to_move`, `elo_opponent`, `elo_diff`, time fields, `phase`, optional `opening_eco` as categorical, clock fields if non-null rate is high.

**Target:** `result_stm` (regression 0–1) or multiclass W/D/L; start with **regression** or **3-class** with LightGBM.

**Artifacts:** Save model + feature list + engine policy under `ep_model/models/` (files gitignored except `.gitkeep`; versioned externally or via small config committed elsewhere if you want).

## Phase D — Product (later)

Expose EP next to Stockfish in ChessCoach: same FEN → eval from engine → EP from model; no change to this plan until A–C are stable.

## Order of implementation

1. Phase A script + minimal Parquet schema (subset of columns if needed).
2. Phase B script + cache + policy file.
3. Phase C training script + metrics (Brier / log-loss by rating bin).

---

*This file is the agreed design reference until superseded.*
