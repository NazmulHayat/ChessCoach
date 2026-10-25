"""
Map ratings from other sites onto the Lichess scale the EP model was trained on.

Chess.com ratings run lower than Lichess ratings, most at the bottom of the range. These linear
fits are rough approximations of commonly cited Chess.com → Lichess comparison tables; they are
meant to put a player in the right neighbourhood, not to be exact.
"""

from __future__ import annotations

# lichess ≈ a * chesscom + b, per time class
_CHESSCOM_TO_LICHESS = {
    "bullet": (0.75, 560.0),
    "blitz": (0.75, 600.0),
    "rapid": (0.70, 740.0),
    "classical": (0.70, 740.0),
}


def detect_pool(headers: dict[str, str]) -> str:
    """'chesscom' for Chess.com PGNs, else 'lichess'."""
    site = (headers.get("Site", "") + " " + headers.get("Link", "")).lower()
    return "chesscom" if "chess.com" in site else "lichess"


def to_lichess_scale(elo: int, pool: str, time_class: str) -> int:
    if pool != "chesscom":
        return elo
    a, b = _CHESSCOM_TO_LICHESS.get(time_class, _CHESSCOM_TO_LICHESS["blitz"])
    return int(round(a * elo + b))


def from_lichess_scale(elo: int, pool: str, time_class: str) -> int:
    """Inverse of to_lichess_scale (e.g. to show an estimate in Chess.com terms), rounded to 10."""
    if pool != "chesscom":
        return elo
    a, b = _CHESSCOM_TO_LICHESS.get(time_class, _CHESSCOM_TO_LICHESS["blitz"])
    return int(round((elo - b) / a, -1))
