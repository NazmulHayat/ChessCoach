"""
Game accuracy, Lichess-style: per-move accuracy from the drop in winning chances, combined with a
volatility-weighted mean and a harmonic mean (so one blunder in a sharp moment counts, which a plain
average hides).

Follows Lichess's published method (lila AccuracyPercent.scala). `lichess_game_accuracy` reproduces it
from engine evals and is checked against the accuracy Lichess shows (scripts/validate_review.py accuracy);
`ep_game_accuracy` applies the same aggregation to our expected-points losses.
"""

from __future__ import annotations

import math
import statistics


def win_percent(cp_white: float) -> float:
    """Lichess win% for white (0-100), cp clipped to ±1000."""
    cp = max(-1000.0, min(1000.0, cp_white))
    return 50.0 + 50.0 * (2.0 / (1.0 + math.exp(-0.00368208 * cp)) - 1.0)


def move_accuracy_pct(drop: float, bonus: float = 1.0) -> float:
    """Accuracy of one move from its win% drop in percentage points (Lichess curve, +1 uncertainty bonus)."""
    if drop <= 0:
        return 100.0
    raw = 103.1668100711649 * math.exp(-0.04354415386753951 * drop) - 3.166924740191411
    return max(0.0, min(100.0, raw + bonus))


def volatility_weights(win_white: list[float]) -> list[float]:
    """
    One weight per move: the standard deviation of white's win% over a sliding window around it, clamped to
    [0.5, 12]. win_white has one entry per position (moves + 1).
    """
    n_moves = len(win_white) - 1
    size = max(2, min(8, n_moves // 10))
    windows = [win_white[:size]] * (size - 2) + [win_white[i : i + size] for i in range(len(win_white) - size + 1)]
    return [max(0.5, min(12.0, statistics.pstdev(w))) for w in windows[:n_moves]]


def _combine(accs: list[float], weights: list[float]) -> float | None:
    if not accs:
        return None
    weighted = sum(a * w for a, w in zip(accs, weights)) / sum(weights)
    # Lichess floors each move at 1 in the harmonic mean; without that one 0-accuracy move zeroes the game
    # (checked against Lichess's own numbers: mean difference 0.32 vs 0.57 with a ~0 floor).
    harmonic = len(accs) / sum(1.0 / max(a, 1.0) for a in accs)
    return (weighted + harmonic) / 2.0


def lichess_game_accuracy(cps_white: list[float], white_starts: bool = True) -> dict[str, float | None]:
    """
    Lichess's game accuracy per colour from white-POV evals (cp, mate mapped to ±1000), one per position
    including the start (Lichess uses +15 cp for the initial position).
    """
    wins = [win_percent(c) for c in cps_white]
    weights = volatility_weights(wins)
    per = {"white": ([], []), "black": ([], [])}
    for i in range(len(wins) - 1):
        white_moved = (i % 2 == 0) == white_starts
        before, after = (wins[i], wins[i + 1]) if white_moved else (100 - wins[i], 100 - wins[i + 1])
        accs, ws = per["white" if white_moved else "black"]
        accs.append(move_accuracy_pct(before - after))
        ws.append(weights[i])
    return {side: _combine(*per[side]) for side in per}


def combine(accs: list[float], weights: list[float]) -> float | None:
    """Lichess's game accuracy from per-move accuracies and their volatility weights."""
    return _combine(accs, weights)


def ep_move_weights(white_ep_by_position: list[float]) -> list[float]:
    """Volatility weights for our review, from white's chances (0-1) per position."""
    return volatility_weights([100.0 * w for w in white_ep_by_position])
