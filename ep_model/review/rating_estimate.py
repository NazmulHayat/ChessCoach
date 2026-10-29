"""
Game rating estimate and opening / middlegame / endgame grades.

Game rating ("you played like a 1700") follows the accuracy shown for the game: X(accuracy) is the rating
whose typical (median) game is played at that accuracy, per time class, fitted on games Lichess already
analysed (scripts/fit_rating_estimate.py). Both players are anchored on the game's average rating, so in
one game the more accurate player never gets the lower game rating:

    game rating = anchor + 400 · tanh((X(accuracy - offset) - anchor) / spread)

`offset` is how much our accuracy runs above Lichess's on the same games (docs/benchmark.md); `spread` is
how widely X - rating varies in that time class (one bullet game says much less than one rapid game), so
the ±400 limit is approached smoothly instead of everyone landing on it.

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
META_FILE = DATA_DIR / "rating_estimate.json"

MIN_MOVES = 10
# Game rating stays within this much of the game's average rating: FIDE's single-game performance bound
# (opponent ± 400). One game says little, so the accuracy curve alone swings too far. A smooth limit
# (tanh) rather than a hard clamp, so two accurate players don't both land on the same capped number.
MAX_SWING = 400.0
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


@lru_cache(maxsize=1)
def load_meta() -> dict[str, Any] | None:
    meta = json.loads(META_FILE.read_text(encoding="utf-8")) if META_FILE.is_file() else None
    return meta if meta and "curves" in meta else None


# Beyond the curve's ends, continue it along the slope of its last EDGE_BINS bins, so more accuracy still
# counts for more (clamping there tied most very accurate players).
EDGE_BINS = 3


def plays_like(accuracy: float, time_class: str, meta: dict[str, Any]) -> float:
    """Rating whose typical game in this time class is played at `accuracy` (our accuracy scale)."""
    curve = meta["curves"].get(time_class) or meta["curves"]["blitz"]
    offset = meta["offset"][time_class] if time_class in meta["offset"] else meta["offset"]["blitz"]
    acc, rating = curve["accuracy"], curve["rating"]
    a = accuracy - offset
    k = min(EDGE_BINS, len(acc) - 1)
    if a < acc[0]:
        return rating[0] + (a - acc[0]) * (rating[k] - rating[0]) / (acc[k] - acc[0])
    if a > acc[-1]:
        return rating[-1] + (a - acc[-1]) * (rating[-1] - rating[-1 - k]) / (acc[-1] - acc[-1 - k])
    return float(np.interp(a, acc, rating))


def game_ratings(
    accuracy: dict[str, float | None],
    ratings: dict[str, float],
    moves: dict[str, int],
    time_class: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, dict[str, float] | None]:
    """
    Game rating per side ({"white": {"plays_like": ...}, "black": ...}) on the Lichess scale, unrounded;
    None for a side with too few moves or without the fitted curves.
    """
    meta = meta or load_meta()
    anchor = (ratings["white"] + ratings["black"]) / 2.0
    out: dict[str, dict[str, float] | None] = {}
    for side in ("white", "black"):
        acc = accuracy.get(side)
        if meta is None or acc is None or moves.get(side, 0) < MIN_MOVES:
            out[side] = None
            continue
        x = plays_like(acc, time_class, meta)
        spread = meta["spread"][time_class] if time_class in meta["spread"] else meta["spread"]["blitz"]
        out[side] = {"plays_like": anchor + MAX_SWING * math.tanh((x - anchor) / spread)}
    return out


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
    from ep_model.review.accuracy import combine

    acc = combine([m["accuracy"] for m in moves], [m.get("weight", 1.0) for m in moves])
    if all(m["ep_label"] == "book" for m in moves):
        grade = "book"
    else:
        grade = next((label for limit, label in PHASE_GRADES if acc >= limit), "blunder")
    return {"accuracy": acc, "grade": grade, "moves": len(moves)}
