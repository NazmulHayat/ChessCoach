"""
Short tactical hints for the coach, from engine mate scores and python-chess attack / exchange checks.

Only the cases a template can state reliably: missed mate, allowing mate, leaving a piece en prise
(static exchange after the move), and a best move that simply wins material.
"""

from __future__ import annotations

import chess

from ep_model.phase_d.special import _capture_value, best_capture_gain

MIN_HANG_POINTS = 1  # report even a hanging pawn, but only for moves already labelled as losing something
MIN_WIN_POINTS = 2


def _piece_on(board: chess.Board, sq: chess.Square) -> str:
    return f"{chess.piece_name(board.piece_type_at(sq))} on {chess.square_name(sq)}"


def hanging_after(board: chess.Board, move: chess.Move) -> tuple[str, int] | None:
    """("knight on f6", points) if the opponent can win material by capture right after `move`."""
    taken = _capture_value(board, move)
    board.push(move)
    try:
        if board.is_checkmate():
            return None
        gain, where = best_capture_gain(board)
        if where is None or gain - taken < MIN_HANG_POINTS:
            return None
        return _piece_on(board, where), gain - taken
    finally:
        board.pop()


def material_won(board: chess.Board, move: chess.Move) -> tuple[str, int] | None:
    """("queen", points) if `move` captures and keeps at least MIN_WIN_POINTS after the best recapture."""
    if not board.is_capture(move):
        return None
    victim = chess.PAWN if board.is_en_passant(move) else board.piece_type_at(move.to_square)
    taken = _capture_value(board, move)
    board.push(move)
    try:
        threat, _ = best_capture_gain(board)
    finally:
        board.pop()
    net = taken - threat
    return (chess.piece_name(victim), net) if net >= MIN_WIN_POINTS else None


def tactic_hint(
    fen_before: str,
    played_uci: str,
    best_uci: str | None,
    mate_before: int | None,
    mate_after_opp: int | None,
) -> str | None:
    """
    One phrase about the played move, e.g. "hangs the knight on f6", "allows mate in 2",
    "missed mate in 3", "missed Nxe5, winning the queen". mate_before is the mover's mate score before
    the move; mate_after_opp is the opponent's mate score after it (positive = opponent mates).
    """
    board = chess.Board(fen_before)
    played = chess.Move.from_uci(played_uci)
    if mate_before is not None and mate_before > 0 and played_uci != best_uci:
        if mate_after_opp is None or mate_after_opp >= 0:
            return f"missed mate in {mate_before}"
    if mate_after_opp is not None and mate_after_opp > 0:
        return f"allows mate in {mate_after_opp}"
    hang = hanging_after(board, played)
    if hang is not None:
        return f"hangs the {hang[0]}"
    if best_uci and best_uci != played_uci:
        best = chess.Move.from_uci(best_uci)
        won = material_won(board, best)
        if won is not None:
            return f"missed {board.san(best)}, winning the {won[0]}"
    return None
