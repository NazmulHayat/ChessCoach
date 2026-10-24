"""Pure helpers: turn python-chess analyse() info into EP columns."""

from __future__ import annotations

import chess


def extract_eval_fields(board: chess.Board, info: dict) -> dict[str, int | None]:
    """
    Map one analyse() result to training columns.
    Centipawn fields are None when the score is mate; mate_* are None when not mate.
    """
    pov = info["score"]
    if pov.turn != board.turn:
        raise ValueError("engine score POV does not match board.turn")

    score_w = pov.white()
    if score_w.is_mate():
        mate_white = score_w.mate()
        eval_cp_white = None
    else:
        mate_white = None
        eval_cp_white = score_w.score()

    score_s = pov.relative
    if score_s.is_mate():
        mate_stm = score_s.mate()
        eval_cp_stm = None
    else:
        mate_stm = None
        eval_cp_stm = score_s.score()

    depth = info.get("depth")
    if depth is not None:
        depth = int(depth)

    return {
        "eval_cp_white": eval_cp_white,
        "mate_white": mate_white,
        "eval_cp_stm": eval_cp_stm,
        "mate_stm": mate_stm,
        "eval_depth": depth,
    }
