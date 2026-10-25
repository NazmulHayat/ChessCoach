"""Phase C features / evaluation helpers and Phase D review helpers (no engine, no model file)."""

import numpy as np
import pandas as pd

from ep_model.phase_c.evaluate import fit_logistic_1d, lichess_expected
from ep_model.phase_c.prepare import FEATURE_NAMES, add_model_features, apply_clock_dropout
from ep_model.phase_d.ratings import detect_pool, to_lichess_scale
from ep_model.phase_d.review import best_move_row, label_for_loss, mirrored_row, move_accuracy


def _row(**kw):
    base = dict(
        ply=10, move_number=5, side_to_move="w", elo_to_move=1500, elo_opponent=1500, elo_diff=0,
        time_class="blitz", initial_time_sec=180, increment_sec=2, clk_white_sec=120.0, clk_black_sec=90.0,
        phase="opening", opening_eco="D02", rating_band="1400-1600",
        eval_cp_white=30, eval_cp_stm=30, mate_white=None, mate_stm=None,
    )
    base.update(kw)
    return base


def test_clock_features_follow_side_to_move():
    df = add_model_features(pd.DataFrame([_row(), _row(side_to_move="b")]))
    assert list(df["clk_stm_sec"]) == [120.0, 90.0]
    assert list(df["clk_opp_sec"]) == [90.0, 120.0]
    assert np.isclose(df["clk_stm_frac"].iloc[0], 120.0 / 180.0)
    assert set(FEATURE_NAMES) <= set(df.columns)


def test_missing_clock_early_is_initial_time_later_is_unknown():
    df = add_model_features(
        pd.DataFrame([_row(ply=1, clk_white_sec=None, clk_black_sec=None), _row(ply=30, clk_white_sec=None, clk_black_sec=None)])
    )
    assert df["clk_stm_sec"].iloc[0] == 180.0
    assert df["clk_stm_sec"].iloc[1] == -1.0
    assert df["clk_stm_frac"].iloc[1] == -1.0


def test_clock_dropout_blanks_whole_games():
    df = pd.DataFrame({"game_id": np.repeat(np.arange(200), 3), "clk_white_sec": 60.0, "clk_black_sec": 60.0})
    out = apply_clock_dropout(df, 0.3, seed=1)
    per_game = out.groupby("game_id")["clk_white_sec"].apply(lambda s: s.isna().all() or s.notna().all())
    assert per_game.all()
    assert 0.15 < out["clk_white_sec"].isna().mean() < 0.45
    assert df["clk_white_sec"].notna().all()


def test_lichess_curve_symmetric_and_clipped():
    assert np.isclose(lichess_expected(np.array([0.0]))[0], 0.5)
    a, b = lichess_expected(np.array([150.0, -150.0]))
    assert np.isclose(a + b, 1.0)
    assert lichess_expected(np.array([5000.0]))[0] == lichess_expected(np.array([1000.0]))[0]


def test_fit_logistic_recovers_parameters():
    rng = np.random.RandomState(0)
    x = rng.uniform(-5, 5, 20000)
    y = (rng.rand(len(x)) < 1 / (1 + np.exp(-(0.3 + 0.8 * x)))).astype(float)
    a, b = fit_logistic_1d(x, y)
    assert abs(a - 0.3) < 0.08 and abs(b - 0.8) < 0.08


def test_label_thresholds():
    assert label_for_loss(0.5, is_engine_best=True) == "best"
    assert label_for_loss(0.01, False) == "excellent"
    assert label_for_loss(0.03, False) == "good"
    assert label_for_loss(0.07, False) == "inaccuracy"
    assert label_for_loss(0.12, False) == "mistake"
    assert label_for_loss(0.19, False) == "mistake"
    assert label_for_loss(0.20, False) == "blunder"


def test_best_move_row_flips_eval_to_opponent():
    before = _row(side_to_move="w", eval_cp_stm=80, eval_cp_white=80)
    after = _row(side_to_move="b", ply=11, eval_cp_stm=200, eval_cp_white=-200)
    r = best_move_row(before, after)
    assert r["side_to_move"] == "b" and r["ply"] == 11
    assert r["eval_cp_stm"] == -80 and r["eval_cp_white"] == 80
    assert r["terminal"] is None


def test_best_move_row_mates():
    after = _row(side_to_move="b")
    r = best_move_row(_row(eval_cp_stm=None, mate_stm=3), after)
    assert r["mate_stm"] == -2 and r["mate_white"] == 2
    assert best_move_row(_row(eval_cp_stm=None, mate_stm=1), after)["terminal"] == 0.0
    assert best_move_row(_row(eval_cp_stm=None, mate_stm=-2), after)["mate_stm"] == 2


def test_mirrored_row_keeps_white_eval_and_swaps_sides():
    r = _row(side_to_move="w", elo_to_move=1500, elo_opponent=1600, elo_diff=-100, eval_cp_stm=80, eval_cp_white=80)
    m = mirrored_row(r)
    assert m["side_to_move"] == "b" and m["elo_to_move"] == 1600 and m["elo_diff"] == 100
    assert m["eval_cp_stm"] == -80 and m["eval_cp_white"] == 80


def test_move_accuracy_curve():
    assert move_accuracy(0.0) > 99.99
    assert 60 < move_accuracy(0.10) < 65
    assert move_accuracy(1.0) == 0.0


def test_rating_pool():
    assert detect_pool({"Site": "Chess.com"}) == "chesscom"
    assert detect_pool({"Site": "https://lichess.org/abc"}) == "lichess"
    assert to_lichess_scale(1500, "lichess", "blitz") == 1500
    assert 1650 < to_lichess_scale(1457, "chesscom", "blitz") < 1750


class _StubModel:
    """EP = 0.5 + eval_cp_stm / 1000 for the side to move (enough to check the plumbing)."""

    def predict_rows(self, rows):
        return np.array([0.5 + (r["eval_cp_stm"] or 0) / 1000.0 for r in rows])


def test_score_attempt_uses_after_context_and_attempt_eval():
    from ep_model.phase_d.review import score_attempt

    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    rows = [_row(), _row(side_to_move="b", ply=2)]
    move = {"ply": 1, "fen_before": fen, "best_uci": "e2e4", "best_san": "e4", "best_line_san": ["e4", "e5"], "ep_best": 0.53}
    calls = []

    def analyse_one(f):
        calls.append(f)
        return {"eval_cp_white": -20, "mate_white": None, "eval_cp_stm": 100, "mate_stm": None, "eval_depth": 10}

    best = score_attempt(rows, move, "e2e4", _StubModel(), analyse_one)
    assert best["correct"] and best["ep_loss"] == 0 and not calls  # engine move: no engine call
    bad = score_attempt(rows, move, "g2g4", _StubModel(), analyse_one)
    assert calls and bad["san"] == "g4"
    assert abs(bad["ep_after"] - 0.4) < 1e-9 and abs(bad["ep_loss"] - 0.13) < 1e-9
    assert not bad["correct"] and bad["label"] == "mistake"
    try:
        score_attempt(rows, move, "e2e5", _StubModel(), analyse_one)
        raise AssertionError("illegal move accepted")
    except ValueError:
        pass


def test_rate_limiter_sliding_window():
    from ep_model.phase_d.server import RateLimiter

    lim = RateLimiter(2, window_sec=10)
    assert lim.allow("a", now=0) and lim.allow("a", now=1)
    assert not lim.allow("a", now=2)
    assert lim.allow("b", now=2)  # per key
    assert lim.allow("a", now=11)  # first event expired
    assert RateLimiter(0).allow("a")  # 0 = unlimited
