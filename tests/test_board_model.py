"""
The shipped board-only model that judges moves. Regression for a real bullet game (lichess.org/nMuWq0F1):
with the clock-aware model, giving up a queen for a rook at equal clocks barely moved the chances and the
move was labelled "good"; Lichess called it a blunder.
"""

import io

import chess.pgn
import numpy as np
import pytest

from ep_model.phase_d.predictor import EPModel, board_model_dir
from ep_model.phase_d.review import label_for_loss, review_game

if not (board_model_dir() / "ep_lgbm.txt").is_file():
    pytest.skip("board model not present", allow_module_level=True)

MODEL = EPModel(board_model_dir())


def _row(cp, elo=1730, clk_w=24.0, clk_b=24.0, time_class="bullet"):
    return dict(
        ply=37, move_number=19, side_to_move="w", elo_to_move=elo, elo_opponent=elo, elo_diff=0,
        white_elo=elo, black_elo=elo, time_class=time_class, initial_time_sec=60, increment_sec=0,
        clk_white_sec=clk_w, clk_black_sec=clk_b, phase="middlegame", opening_eco="B13", rating_band="1600-1800",
        eval_cp_stm=cp, eval_cp_white=cp, mate_stm=None, mate_white=None,
    )


def test_board_model_has_no_clock_features():
    assert not any(f.startswith("clk_") for f in MODEL.feature_names)
    a = MODEL.predict_rows([_row(100, clk_w=24, clk_b=12)])
    b = MODEL.predict_rows([_row(100, clk_w=12, clk_b=24)])
    assert np.allclose(a, b)


@pytest.mark.parametrize("elo", [800, 1300, 1730, 2300])
def test_better_eval_never_lowers_chances(elo):
    cps = list(range(-1500, 1501, 25))
    ep = MODEL.predict_rows([_row(cp, elo=elo) for cp in cps])
    assert np.all(np.diff(ep) >= -1e-9)


def test_queen_for_rook_is_at_least_a_mistake():
    # Opponent to move after the mover's best move (+62 for the opponent's side flipped) vs after Qxf1+ (+365).
    best, after = MODEL.predict_rows([_row(62), _row(365)])
    loss = after - best  # the mover's loss = the opponent's gain
    assert label_for_loss(loss, is_engine_best=False) in ("mistake", "blunder")


class _SideModel:
    """0.8 for white to move, 0.4 for black: the bar should show 0.7 for white everywhere."""

    def predict_rows(self, rows):
        return np.array([0.8 if r["side_to_move"] == "w" else 0.4 for r in rows])


def test_labels_use_judge_model_and_bar_uses_chances_model():
    game = chess.pgn.read_game(io.StringIO('[TimeControl "60+0"]\n\n1. e4 e5 2. Qh5 Nc6 *'))
    evals = lambda fens, _p: [  # noqa: E731
        {"eval_cp_white": 0, "mate_white": None, "eval_cp_stm": 0, "mate_stm": None, "eval_depth": 1, "best_uci": None}
        for _ in fens
    ]
    r = review_game(game, MODEL, evals, 1, 1500, 1500, book_path=None, chances_model=_SideModel())
    assert all(abs(p["white_ep"] - 0.7) < 1e-9 for p in r["positions"])
    assert all(m["ep_loss"] == 0 for m in r["moves"])  # judged by MODEL: same eval before and after
