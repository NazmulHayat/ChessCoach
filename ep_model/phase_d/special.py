"""
Great / Miss / Brilliant labels: our own documented rules on top of the EP bands (see docs/methodology.md).

Chess.com describes these labels only in words; these rules follow that wording with expected points:

- Great: the engine's best move, where the second-best move is much worse (an "only move"), or where the
  best move keeps a better outcome band (losing / equal / winning) than the second-best one.
- Miss: the opponent just made a mistake or blunder and this move gives back most of what they gave away,
  without dropping below where the mover stood before the gift (that would be a plain mistake/blunder).
- Brilliant: a best or near-best move that gives up material (static exchange) when a safer move existed,
  leaves the mover at least equal, and wasn't needed because the position was already completely winning.

Rating-dependent thresholds: the EP curve is steeper at higher ratings (the same engine gap costs more
points), so the Great gap grows with rating; the Brilliant tolerance shrinks with rating, like Chess.com
being more generous with Brilliant at lower levels.
"""

from __future__ import annotations

from dataclasses import dataclass

import chess

PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}

# Outcome bands on the mover's EP.
LOSING_BELOW = 0.30
WINNING_ABOVE = 0.70

# Great: also fires on an outcome-band change, but only with at least this gap (avoids 0.71 vs 0.69).
GREAT_BAND_MIN_GAP = 0.05
# Brilliant: points of material given up, after the move and the opponent's best capture sequence.
SAC_MIN_POINTS = 2
BRILLIANT_MIN_EP_AFTER = 0.45  # not worse than about equal after the sacrifice
BRILLIANT_WINNING_CAP = 0.90  # if the second-best move already keeps this much, the sac wasn't needed
# Miss: the opponent's gift must be at least mistake-sized, and this move must give back this share of it.
MISS_MIN_GIFT = 0.10
MISS_GIVE_BACK = 0.5
MISS_MIN_LOSS = 0.05
MISS_FLOOR_MARGIN = 0.05


@dataclass(frozen=True)
class Thresholds:
    great_gap: float
    brilliant_max_loss: float


def _lerp_by_elo(elo: float, lo: float, hi: float, elo_lo: float = 1000.0, elo_hi: float = 2200.0) -> float:
    t = min(1.0, max(0.0, (elo - elo_lo) / (elo_hi - elo_lo)))
    return lo + t * (hi - lo)


def thresholds_for(elo: float) -> Thresholds:
    """Great gap 0.10 → 0.15 and Brilliant tolerance 0.03 → 0.01, linear from 1000 to 2200 (Lichess scale)."""
    return Thresholds(great_gap=_lerp_by_elo(elo, 0.10, 0.15), brilliant_max_loss=_lerp_by_elo(elo, 0.03, 0.01))


def outcome_band(ep: float) -> int:
    """0 losing, 1 about equal, 2 winning (mover's EP)."""
    return 0 if ep < LOSING_BELOW else 2 if ep > WINNING_ABOVE else 1


# ---------- material ----------


def _capture_value(board: chess.Board, move: chess.Move) -> int:
    """Material won by `move` itself: the captured piece plus any promotion gain."""
    value = 0
    if board.is_en_passant(move):
        value = PIECE_VALUES[chess.PAWN]
    else:
        victim = board.piece_type_at(move.to_square)
        if victim is not None:
            value = PIECE_VALUES[victim]
    if move.promotion:
        value += PIECE_VALUES[move.promotion] - PIECE_VALUES[chess.PAWN]
    return value


def see(board: chess.Board, square: chess.Square) -> int:
    """
    Static exchange on `square` for the side to move: material it wins by capturing there with the least
    valuable piece first, with either side free to stop. Uses legal moves, so pins and x-rays count.
    """
    if board.piece_at(square) is None or not board.attackers(board.turn, square):
        return 0
    captures = [m for m in board.legal_moves if m.to_square == square]
    if not captures:
        return 0
    move = min(
        captures,
        key=lambda m: (PIECE_VALUES[board.piece_type_at(m.from_square)] or 100, -(PIECE_VALUES[m.promotion] if m.promotion else 0)),
    )
    gain = _capture_value(board, move)
    board.push(move)
    try:
        return max(0, gain - see(board, square))
    finally:
        board.pop()


def best_capture_gain(board: chess.Board) -> tuple[int, chess.Square | None]:
    """Most material the side to move can win right now by a capture sequence on one square, and where."""
    best, where = 0, None
    them = not board.turn
    for sq in chess.SquareSet(board.occupied_co[them]):
        if board.piece_type_at(sq) == chess.KING:
            continue
        g = see(board, sq)
        if g > best:
            best, where = g, sq
    return best, where


def sacrificed_piece(board: chess.Board, move: chess.Move) -> str | None:
    """Name of the mover's piece the opponent can win after `move` ("queen", "knight", …)."""
    board.push(move)
    try:
        _, where = best_capture_gain(board)
        return chess.piece_name(board.piece_type_at(where)) if where is not None else None
    finally:
        board.pop()


def material_given(board: chess.Board, move: chess.Move) -> int:
    """
    Points the mover stands to lose with `move`: what the opponent can then win by capture, minus what
    the move itself captured. Bxf7+ Kxf7 gives 3 - 1 = 2; a defended trade gives 0.
    """
    taken = _capture_value(board, move)
    board.push(move)
    try:
        if board.is_checkmate():
            return 0
        threat, _ = best_capture_gain(board)
    finally:
        board.pop()
    return threat - taken


def sacrifice_points(board: chess.Board, move: chess.Move) -> int:
    """
    Material sacrificed by `move` relative to the safest legal alternative (so a piece that was going to be
    lost anyway, e.g. trapped, doesn't count). 0 when the move gives up less than SAC_MIN_POINTS.
    """
    given = material_given(board, move)
    if given < SAC_MIN_POINTS:
        return 0
    others = [m for m in board.legal_moves if m != move]
    if not others:
        return 0
    safest = min(material_given(board, m) for m in others)
    return given if given - safest >= SAC_MIN_POINTS else 0


# ---------- label rules (mover's point of view) ----------


def is_great(
    is_best: bool,
    ep_best: float,
    ep_second: float | None,
    elo: float,
    legal_moves: int,
    is_obvious_recapture: bool,
    gives_mate: bool = False,
) -> bool:
    """Forced moves, obvious recaptures and mate-in-one are just "best"."""
    if not is_best or ep_second is None or legal_moves < 2 or is_obvious_recapture or gives_mate:
        return False
    gap = ep_best - ep_second
    if gap >= thresholds_for(elo).great_gap:
        return True
    return gap >= GREAT_BAND_MIN_GAP and outcome_band(ep_best) > outcome_band(ep_second)


def is_miss(
    is_best: bool,
    ep_loss: float,
    ep_after: float,
    opp_prev_loss: float | None,
    mover_ep_before_gift: float | None,
) -> bool:
    """
    opp_prev_loss: EP the opponent gave away on their previous move. mover_ep_before_gift: the mover's EP
    before that move (1 - the opponent's EP had they played best).
    """
    if is_best or opp_prev_loss is None or mover_ep_before_gift is None or opp_prev_loss < MISS_MIN_GIFT:
        return False
    if ep_loss < max(MISS_MIN_LOSS, MISS_GIVE_BACK * opp_prev_loss):
        return False
    return ep_after >= mover_ep_before_gift - MISS_FLOOR_MARGIN


def is_brilliant(ep_loss: float, ep_after: float, ep_second: float | None, elo: float, sac_points: int) -> bool:
    if sac_points < SAC_MIN_POINTS or ep_loss > thresholds_for(elo).brilliant_max_loss:
        return False
    if ep_after < BRILLIANT_MIN_EP_AFTER:
        return False
    # Already completely winning without the sacrifice?
    return ep_second is None or ep_second < BRILLIANT_WINNING_CAP
