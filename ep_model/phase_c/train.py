"""
Train LightGBM EP regressor on Phase B Parquet. Split by game_id (no row leakage).

Usage (repo root):
  python -m ep_model.phase_c.train -v
  python -m ep_model.phase_c.train --max-rows 5000 --val-fraction 0.15
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np

import pandas as pd

from ep_model.phase_c.prepare import (
    CATEGORICAL_FEATURES,
    TRAIN_COLUMNS,
    apply_clock_dropout,
    build_training_frame,
    load_eval_parquet,
    load_eval_parquet_sharded,
    metrics_by_rating_band,
    metrics_regression,
    split_by_game_id,
    split_game_ids,
    unique_game_ids_from_parquets,
)

LOG = logging.getLogger(__name__)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_input_globs(processed: Path, pattern: str = "rows_with_eval_part*.parquet") -> list[Path]:
    return sorted(processed.glob(pattern))


def run(
    input_paths: list[Path],
    out_dir: Path,
    val_fraction: float,
    seed: int,
    max_rows: int | None,
    policy_path: Path | None,
    sharded_load: bool = False,
    clock_dropout: float = 0.15,
    num_leaves: int = 31,
) -> int:
    if not input_paths:
        LOG.error("No input Parquet files (rows_with_eval_part*.parquet)")
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)

    train_gids: set | None = None
    val_gids: set | None = None

    if sharded_load:
        if max_rows is not None:
            LOG.warning("--max-rows is ignored with --sharded-load (full train/val load)")
        LOG.info("Sharded load: scanning game_id across %s Parquet file(s)", len(input_paths))
        ug = unique_game_ids_from_parquets(input_paths)
        train_gids, val_gids = split_game_ids(ug, val_fraction=val_fraction, seed=seed)
        raw_tr, raw_va = load_eval_parquet_sharded(input_paths, train_gids, val_gids)
        df = pd.concat([raw_tr, raw_va], ignore_index=True)
        del raw_tr, raw_va
        LOG.info("Sharded load done: %s rows", len(df))
    else:
        LOG.info("Loading %s Parquet file(s)", len(input_paths))
        df = load_eval_parquet(input_paths, columns=TRAIN_COLUMNS, max_rows=max_rows, seed=seed)
        LOG.info("Loaded %s rows", len(df))

    df = apply_clock_dropout(df, clock_dropout, seed, inplace=True)
    df, feature_names, target_col = build_training_frame(df, copy=False)
    LOG.info("Rows after filter: %s, games: %s", len(df), df["game_id"].nunique())

    if sharded_load and train_gids is not None and val_gids is not None:
        train_df = df[df["game_id"].isin(train_gids)]
        val_df = df[df["game_id"].isin(val_gids)]
    else:
        train_df, val_df = split_by_game_id(df, val_fraction=val_fraction, seed=seed)
    LOG.info("Train rows=%s games=%s | Val rows=%s games=%s", len(train_df), train_df["game_id"].nunique(), len(val_df), val_df["game_id"].nunique())

    X_train = train_df[feature_names]
    y_train = train_df[target_col].to_numpy(dtype=np.float64)
    X_val = val_df[feature_names]
    y_val = val_df[target_col].to_numpy(dtype=np.float64)

    train_set = lgb.Dataset(
        X_train,
        label=y_train,
        feature_name=feature_names,
        categorical_feature=[c for c in CATEGORICAL_FEATURES if c in feature_names],
        free_raw_data=True,
    )
    val_set = lgb.Dataset(
        X_val,
        label=y_val,
        feature_name=feature_names,
        categorical_feature=[c for c in CATEGORICAL_FEATURES if c in feature_names],
        reference=train_set,
        free_raw_data=False,
    )

    params = {
        # Target is an expected score in [0, 1] (draw = 0.5): cross-entropy gives calibrated
        # probabilities, unlike L2/MAE which pull predictions toward 0 / 0.5 / 1.
        "objective": "cross_entropy",
        "metric": ["cross_entropy", "l2"],
        "first_metric_only": True,
        "verbosity": -1,
        "seed": seed,
        "num_leaves": num_leaves,
        "learning_rate": 0.05,
        "feature_fraction": 0.9,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        # Scales with data, capped so very large runs can still learn fine-grained structure.
        "min_data_in_leaf": max(5, min(len(train_df) // 500, 2000)),
    }

    t0 = time.perf_counter()
    evals_result: dict = {}
    booster = lgb.train(
        params,
        train_set,
        valid_sets=[train_set, val_set],
        valid_names=["train", "val"],
        num_boost_round=2000,
        callbacks=[
            lgb.early_stopping(stopping_rounds=50, verbose=False),
            lgb.record_evaluation(evals_result),
        ],
    )
    train_time = time.perf_counter() - t0

    pred_val = booster.predict(X_val, num_iteration=booster.best_iteration)
    m = metrics_regression(y_val, pred_val)
    by_band = metrics_by_rating_band(y_val, pred_val, val_df["rating_band"])

    LOG.info(
        "Val metrics: LogLoss=%.4f MAE=%.4f RMSE=%.4f Brier(clipped pred)=%.4f | best_iter=%s | train_time=%.1fs",
        m["log_loss"],
        m["mae"],
        m["rmse"],
        m["brier_clipped"],
        booster.best_iteration,
        train_time,
    )
    if by_band:
        LOG.info("Val MAE by rating_band (n>=5): %s", {k: round(v["mae"], 4) for k, v in by_band.items()})

    model_path = out_dir / "ep_lgbm.txt"
    booster.save_model(str(model_path))
    LOG.info("Saved model %s", model_path)

    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "n_rows": int(len(df)),
        "n_games": int(df["game_id"].nunique()),
        "val_fraction": val_fraction,
        "seed": seed,
        "feature_names": feature_names,
        "categorical_features": [c for c in CATEGORICAL_FEATURES if c in feature_names],
        "target": target_col,
        "lgbm_params": {k: v for k, v in params.items() if k != "verbosity"},
        "clock_dropout": clock_dropout,
        "best_iteration": int(booster.best_iteration),
        "val_metrics": m,
        "val_metrics_by_rating_band": by_band,
        "train_time_sec": train_time,
        "input_files": [str(p.name) for p in input_paths],
        "input_dir": str(input_paths[0].parent),
        "engine_policy_path": str(policy_path) if policy_path and policy_path.is_file() else None,
    }
    # Held-out games, so evaluate.py scores exactly the rows the model never saw.
    val_ids_path = out_dir / "ep_val_game_ids.txt"
    val_ids_path.write_text("\n".join(sorted(map(str, val_df["game_id"].unique()))) + "\n", encoding="utf-8")

    manifest_path = out_dir / "ep_train_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    LOG.info("Saved manifest %s", manifest_path)

    return 0


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    proc = root / "ep_model" / "processed"
    models = root / "ep_model" / "models"
    policy = root / "ep_model" / "config" / "engine_policy.json"

    p = argparse.ArgumentParser(description="Phase C: train EP LightGBM on rows_with_eval Parquet")
    p.add_argument("--processed-dir", type=Path, default=proc)
    p.add_argument("--pattern", default="rows_with_eval_part*.parquet", help="Shard glob inside --processed-dir")
    p.add_argument("--num-leaves", type=int, default=31)
    p.add_argument("--output-dir", type=Path, default=models)
    p.add_argument("--val-fraction", type=float, default=0.15)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--max-rows", type=int, default=None, help="Cap rows (shards read in random order until reached)")
    p.add_argument(
        "--sharded-load",
        action="store_true",
        help="Read one Parquet shard at a time (lower peak RAM for large Phase B output)",
    )
    p.add_argument("--policy", type=Path, default=policy, help="Engine policy path for manifest")
    p.add_argument(
        "--clock-dropout",
        type=float,
        default=0.15,
        help="Fraction of games trained with clocks blanked (teaches a clock-unknown mode)",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    paths = default_input_globs(args.processed_dir, args.pattern)
    return run(
        input_paths=paths,
        out_dir=args.output_dir,
        val_fraction=args.val_fraction,
        seed=args.seed,
        max_rows=args.max_rows,
        policy_path=args.policy,
        sharded_load=args.sharded_load,
        clock_dropout=args.clock_dropout,
        num_leaves=args.num_leaves,
    )


if __name__ == "__main__":
    sys.exit(main())
