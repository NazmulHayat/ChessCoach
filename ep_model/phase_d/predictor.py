"""Load the trained EP model and score Phase B-shaped rows (FEN context + engine eval)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

from ep_model.phase_c.prepare import add_model_features


def default_model_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "models"


class EPModel:
    """
    Wraps ep_lgbm.txt + ep_train_manifest.json.

    Rows use the same columns Phase B writes (side_to_move, elos, clocks, time fields, phase,
    opening_eco, rating_band, eval_cp_* / mate_*, eval_depth, ply, move_number). LightGBM keeps the
    training category lists inside the model file, so categorical values map to the same codes.
    """

    def __init__(self, model_dir: Path | None = None):
        model_dir = model_dir or default_model_dir()
        self.booster = lgb.Booster(model_file=str(model_dir / "ep_lgbm.txt"))
        with open(model_dir / "ep_train_manifest.json", encoding="utf-8") as f:
            self.manifest = json.load(f)
        self.feature_names: list[str] = self.manifest["feature_names"]

    def predict_rows(self, rows: list[dict[str, Any]]) -> np.ndarray:
        """Expected score in [0, 1] for the side to move in each row."""
        if not rows:
            return np.zeros(0)
        df = add_model_features(pd.DataFrame(rows))
        return np.clip(self.booster.predict(df[self.feature_names]), 0.0, 1.0)
