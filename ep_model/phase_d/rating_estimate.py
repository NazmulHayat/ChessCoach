"""
Game rating estimate and opening / middlegame / endgame grades.

Rating estimate ("you played like a 1650"): a small LightGBM model (scripts/fit_rating_estimate.py) turns
rating-free accuracy features of one player's moves in one game into a quality score, and the shown rating
is the one whose typical (median) score matches it. Fitted on games Lichess already analysed. The features use the Lichess win% curve on raw engine evals (not the EP model, which takes the
rating as an input, and not zeroing the engine's own move, which the fitting data can't know).

Phases (Lichess-style material rules): endgame once at most 6 queens / rooks / bishops / knights are left
on the board; opening for the first 10 moves (or longer while still in book); middlegame otherwise.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

import chess
import numpy as np

DATA_DIR = Path(__file__).resolve().parent / "data"
MODEL_FILE = DATA_DIR / "rating_lgbm.txt"
META_FILE = DATA_DIR / "rating_estimate.json"
FEATURE_NAMES = [
    "accuracy",
    "blunder_rate",
    "mistake_rate",
    "inaccuracy_rate",
    "precise_rate",
    "log_moves",
    "mean_abs_cp",
    "balanced_accuracy",
    "balanced_share",
    "time_class",
]
TIME_CLASSES = {"bullet": 0, "blitz": 1, "rapid": 2, "classical": 3}
BALANCED_CP = 300  # |eval| below this counts as a roughly balanced position

MIN_MOVES = 10
OPENING_PLIES = 20
ENDGAME_MAX_PIECES = 6

# Phase accuracy -> grade, shown with the label icons. Book-only phases get "book".
PHASE_GRADES = [(95.0, "best"), (85.0, "excellent"), (75.0, "good"), (60.0, "inaccuracy"), (45.0, "mistake")]


def win_prob(cp_mover: float) -> float:
    """Lichess win% curve for the mover, cp clipped to ±1000."""
    cp = max(-1000.0, min(1000.0, cp_mover))
    return 1.0 / (1.0 + math.exp(-0.00368208 * cp))


def move_accuracy(loss: float) -> float:
    """Lichess's per-move accuracy curve, on an expected-score drop in [0, 1]."""
    return max(0.0, min(100.0, 103.1668 * math.exp(-0.04354 * loss * 100.0) - 3.1669))


def features(losses: list[float], abs_cp_before: list[float], time_class: str) -> list[float]:
    """
    One player's moves in one game: raw win% drop per move and |engine eval| (cp, mover's view) before it.
    Accuracy in balanced positions and the mean |eval| separate "accurate because the game was easy"
    from "accurate in a real fight".
    """
    n = max(1, len(losses))
    acc = [move_accuracy(x) for x in losses]
    cps = [min(abs(c), 1000.0) for c in abs_cp_before]
    bal = [a for a, c in zip(acc, cps) if c < BALANCED_CP]
    mean_acc = sum(acc) / n
    return [
        mean_acc,
        sum(1 for x in losses if x >= 0.20) / n,
        sum(1 for x in losses if 0.10 <= x < 0.20) / n,
        sum(1 for x in losses if 0.05 <= x < 0.10) / n,
        sum(1 for x in losses if x < 0.01) / n,
        math.log(n),
        sum(cps) / max(1, len(cps)),
        sum(bal) / len(bal) if bal else mean_acc,
        len(bal) / n,
        float(TIME_CLASSES.get(time_class, 1)),
    ]


@lru_cache(maxsize=1)
def _model() -> tuple[Any, dict[str, Any]] | None:
    if not (MODEL_FILE.is_file() and META_FILE.is_file()):
        return None
    import lightgbm as lgb

    return lgb.Booster(model_file=str(MODEL_FILE)), json.loads(META_FILE.read_text(encoding="utf-8"))


def estimate_rating(
    losses: list[float], abs_cp_before: list[float], time_class: str, player_rating: float
) -> dict[str, int] | None:
    """
    Game (performance) rating on the Lichess scale: your rating moved by how much better or worse you played
    than players at your rating typically do. {"rating", "low", "high", "plays_like"}; None without a model
    or with too few moves.
    """
    loaded = _model()
    if loaded is None or len(losses) < MIN_MOVES:
        return None
    booster, meta = loaded
    score = float(booster.predict([features(losses, abs_cp_before, time_class)])[0])
    table = meta["inverse"].get(time_class) or meta["inverse"]["blitz"]
    plays_like = float(np.interp(score, table["score"], table["rating"]))
    r = player_rating + table["k"] * (plays_like - player_rating)
    sd = meta["posterior_sd"].get(time_class) or meta["posterior_sd"]["blitz"]
    return {
        "rating": int(round(r, -1)),
        "low": int(round(r - sd, -1)),
        "high": int(round(r + sd, -1)),
        "plays_like": int(round(plays_like, -1)),
    }


def phase_of(board: chess.Board, ply: int, in_book: bool) -> str:
    """Phase of the position `board` (before the move at 1-based `ply`)."""
    pieces = sum(
        len(board.pieces(pt, color)) for pt in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT) for color in chess.COLORS
    )
    if pieces <= ENDGAME_MAX_PIECES:
        return "endgame"
    if ply <= OPENING_PLIES or in_book:
        return "opening"
    return "middlegame"


def phase_grade(moves: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Accuracy and grade label for one player's moves in one phase; None if they made no moves there."""
    if not moves:
        return None
    from ep_model.phase_d.accuracy import combine

    acc = combine([m["accuracy"] for m in moves], [m.get("weight", 1.0) for m in moves])
    if all(m["ep_label"] == "book" for m in moves):
        grade = "book"
    else:
        grade = next((label for limit, label in PHASE_GRADES if acc >= limit), "blunder")
    return {"accuracy": acc, "grade": grade, "moves": len(moves)}
