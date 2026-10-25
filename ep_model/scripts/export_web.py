"""
Export what the in-browser review needs into web/public/data:

  models/board.json    move-judging EP model (labels, accuracy)
  models/chances.json  clock-aware EP model (eval bar, graph)
  models/rating.json   game-rating quality model + its meta (inverse tables)
  polyglot.json        the 781 Polyglot Zobrist keys (hex), for reading the opening book
  book.bin             the opening book itself

Trees are flattened per tree: f (feature index), t (threshold or category list), c (1 = categorical split),
dl (default left), m (missing type: 0 none, 1 zero, 2 NaN), l / r (child: >= 0 node, < 0 leaf ~index), v (leaves).

Also writes parity fixtures (web/src/review/__fixtures__): model inputs with Python's predictions, and full
Python reviews of benchmark games with their cached engine fields, so the TypeScript port is tested against
the Python reference.

Usage (repo root):
  python -m ep_model.scripts.export_web
"""

from __future__ import annotations

import json
import random
import shutil
import sys
from pathlib import Path
from typing import Any

import chess.polyglot
import lightgbm as lgb
import pandas as pd

from ep_model.phase_c.prepare import add_model_features
from ep_model.phase_d.predictor import EPModel, board_model_dir, default_model_dir

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "web" / "public" / "data"
FIXTURES = REPO / "web" / "src" / "review" / "__fixtures__"
MISSING = {"None": 0, "Zero": 1, "NaN": 2}


def flatten(tree: dict[str, Any]) -> dict[str, list]:
    t: dict[str, list] = {k: [] for k in ("f", "t", "c", "dl", "m", "l", "r", "v")}

    def walk(node: dict[str, Any]) -> int:
        if "leaf_value" in node:
            t["v"].append(node["leaf_value"])
            return ~(len(t["v"]) - 1)
        i = len(t["f"])
        cat = node["decision_type"] == "=="
        t["f"].append(node["split_feature"])
        t["t"].append([int(x) for x in str(node["threshold"]).split("||")] if cat else node["threshold"])
        t["c"].append(int(cat))
        t["dl"].append(int(node["default_left"]))
        t["m"].append(MISSING[node["missing_type"]])
        t["l"].append(0)
        t["r"].append(0)
        t["l"][i] = walk(node["left_child"])
        t["r"][i] = walk(node["right_child"])
        return i

    walk(tree["tree_structure"])
    return t


def export_booster(booster: lgb.Booster, path: Path, extra: dict[str, Any] | None = None) -> None:
    m = booster.dump_model()
    names = m["feature_names"]
    cats = {}
    if booster.pandas_categorical:
        cat_names = [n for i, n in enumerate(names) if i in set(m.get("categorical_feature", []))] or [
            n for n in ("phase", "time_class", "rating_band", "opening_eco") if n in names
        ]
        cats = {n: [str(v) for v in vals] for n, vals in zip(cat_names, booster.pandas_categorical)}
    out = {
        "objective": "sigmoid" if m["objective"].startswith(("cross_entropy", "binary")) else "identity",
        "features": names,
        "categorical": cats,
        "trees": [flatten(t) for t in m["tree_info"]],
        **(extra or {}),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"{path.relative_to(REPO)}: {len(out['trees'])} trees, {path.stat().st_size / 1e6:.1f} MB")


def model_rows(n: int, seed: int = 3) -> list[dict[str, Any]]:
    """Varied Phase B-shaped rows (incl. mate scores, missing clocks, unknown categories)."""
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        side = rng.choice("wb")
        elo_m, elo_o = rng.randint(400, 2800), rng.randint(400, 2800)
        mate = rng.choice([None] * 8 + [1, -1, 3, -4, 12])
        cp = None if mate is not None else rng.choice([rng.randint(-300, 300), rng.randint(-2000, 2000), 0])
        sign = 1 if side == "w" else -1
        init = rng.choice([60, 180, 300, 600, 900, 1800, None])
        ply = rng.randint(1, 160)
        rows.append(
            {
                "ply": ply, "move_number": (ply + 1) // 2, "side_to_move": side,
                "elo_to_move": elo_m, "elo_opponent": elo_o, "elo_diff": elo_m - elo_o,
                "white_elo": elo_m if side == "w" else elo_o, "black_elo": elo_o if side == "w" else elo_m,
                "time_class": rng.choice(["bullet", "blitz", "rapid", "classical", "unknown"]),
                "initial_time_sec": init, "increment_sec": rng.choice([0, 1, 2, 5, None]),
                "clk_white_sec": rng.choice([None, rng.uniform(0, 1800)]), "clk_black_sec": rng.choice([None, rng.uniform(0, 1800)]),
                "phase": rng.choice(["opening", "middlegame", "endgame"]),
                "opening_eco": rng.choice(["B13", "C50", "A00", "E99", None, "Z99"]),
                "rating_band": rng.choice(["0-1000", "1000-1200", "1400-1600", "1600-1800", "2000-3000", "2000+"]),
                "eval_cp_stm": cp, "mate_stm": mate,
                "eval_cp_white": None if cp is None else sign * cp, "mate_white": None if mate is None else sign * mate,
            }
        )
    return rows


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    board, chances = EPModel(board_model_dir()), EPModel(default_model_dir())
    export_booster(board.booster, OUT / "models" / "board.json")
    export_booster(chances.booster, OUT / "models" / "chances.json")
    rating_dir = REPO / "ep_model" / "phase_d" / "data"
    meta = json.loads((rating_dir / "rating_estimate.json").read_text(encoding="utf-8"))
    export_booster(
        lgb.Booster(model_file=str(rating_dir / "rating_lgbm.txt")),
        OUT / "models" / "rating.json",
        {"inverse": meta["inverse"], "posterior_sd": meta["posterior_sd"]},
    )
    (OUT / "polyglot.json").write_text(json.dumps([f"{x:016x}" for x in chess.polyglot.POLYGLOT_RANDOM_ARRAY]), encoding="utf-8")
    shutil.copy(rating_dir / "book.bin", OUT / "book.bin")

    # Model parity fixture: rows, the features Python builds, and both models' predictions.
    rows = model_rows(400)
    feats = add_model_features(pd.DataFrame(rows))
    (FIXTURES / "model_rows.json").write_text(
        json.dumps(
            {
                "rows": rows,
                "features": feats[chances.feature_names].astype(object).where(feats[chances.feature_names].notna(), None).values.tolist(),
                "board": board.predict_rows(rows).tolist(),
                "chances": chances.predict_rows(rows).tolist(),
            }
        ),
        encoding="utf-8",
    )
    print("fixtures: model_rows.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
