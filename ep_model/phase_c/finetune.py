"""
Fine-tune a large pretrained EP model (e.g. trained on harvested Lichess server evals) on the
clean Stockfish-labelled Phase B rows, so it adapts to our engine's eval scale.

The Phase B held-out test games (`--test-ids`, written by phase_c.train) are never used here: the
remaining Phase B games are split into a fit set and an early-stopping set.

Usage (repo root):
  python -m ep_model.phase_c.finetune --base-model ep_model/models_lichess --output-dir ep_model/models_finetuned
  python -m ep_model.phase_c.evaluate --extra-model ep_finetuned=ep_model/models_finetuned
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb

from ep_model.phase_c.prepare import (
    CATEGORICAL_FEATURES,
    TRAIN_COLUMNS,
    build_training_frame,
    load_eval_parquet,
    metrics_regression,
    monotone_constraints,
    split_game_ids,
)

LOG = logging.getLogger(__name__)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def run(base_dir: Path, processed: Path, test_ids_path: Path, out_dir: Path, learning_rate: float, seed: int) -> int:
    paths = sorted(processed.glob("rows_with_eval_part*.parquet"))
    df, features, target = build_training_frame(load_eval_parquet(paths, columns=TRAIN_COLUMNS), copy=False)
    with open(base_dir / "ep_train_manifest.json", encoding="utf-8") as f:
        base_manifest = json.load(f)
    if base_manifest.get("time_classes"):  # same data scope as the pretrained model
        df = df[df["time_class"].astype(str).isin(base_manifest["time_classes"])]
    test_ids = set(test_ids_path.read_text(encoding="utf-8").split())
    rest = df[~df["game_id"].astype(str).isin(test_ids)]
    fit_ids, stop_ids = split_game_ids(rest["game_id"].astype(str).unique(), 0.15, seed)
    gid = rest["game_id"].astype(str)
    fit, stop = rest[gid.isin(fit_ids)], rest[gid.isin(stop_ids)]
    LOG.info("Fine-tune rows: fit=%s stop=%s (test games excluded: %s)", len(fit), len(stop), len(test_ids))

    base = lgb.Booster(model_file=str(base_dir / "ep_lgbm.txt"))
    features = base.feature_name()  # the base model's features (all, or the board-only set)
    params = {
        "objective": "cross_entropy",
        "metric": "cross_entropy",
        "verbosity": -1,
        "seed": seed,
        "learning_rate": learning_rate,
        "num_leaves": 31,
        "min_data_in_leaf": 200,
        "feature_fraction": 0.9,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "monotone_constraints": monotone_constraints(features),
    }
    cats = [c for c in CATEGORICAL_FEATURES if c in features]
    d_fit = lgb.Dataset(fit[features], fit[target], categorical_feature=cats, free_raw_data=False)
    d_stop = lgb.Dataset(stop[features], stop[target], reference=d_fit, free_raw_data=False)
    booster = lgb.train(
        params, d_fit, num_boost_round=2000, valid_sets=[d_stop], init_model=base,
        callbacks=[lgb.early_stopping(50, verbose=False)],
    )
    extra = booster.best_iteration - base.num_trees()
    stop_metrics = metrics_regression(stop[target].to_numpy(), booster.predict(stop[features], num_iteration=booster.best_iteration))
    LOG.info("Added %s trees on top of %s | early-stopping set log loss %.4f", extra, base.num_trees(), stop_metrics["log_loss"])

    out_dir.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(out_dir / "ep_lgbm.txt"), num_iteration=booster.best_iteration)
    manifest = {
        **base_manifest,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "finetune": {
            "base_model_dir": str(base_dir),
            "base_trees": base.num_trees(),
            "added_trees": extra,
            "learning_rate": learning_rate,
            "fit_rows": len(fit),
            "stop_rows": len(stop),
            "stop_metrics": stop_metrics,
        },
    }
    (out_dir / "ep_train_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    shutil.copy(test_ids_path, out_dir / "ep_val_game_ids.txt")
    LOG.info("Saved %s", out_dir)
    return 0


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    p = argparse.ArgumentParser(description="Fine-tune a pretrained EP model on clean Phase B rows")
    p.add_argument("--base-model", type=Path, default=root / "ep_model" / "models_lichess")
    p.add_argument("--processed-dir", type=Path, default=root / "ep_model" / "processed")
    p.add_argument("--test-ids", type=Path, default=root / "ep_model" / "models" / "ep_val_game_ids.txt")
    p.add_argument("--output-dir", type=Path, default=root / "ep_model" / "models_finetuned")
    p.add_argument("--learning-rate", type=float, default=0.03)
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return run(args.base_model, args.processed_dir, args.test_ids, args.output_dir, args.learning_rate, args.seed)


if __name__ == "__main__":
    sys.exit(main())
