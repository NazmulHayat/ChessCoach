"""Phase C features / evaluation helpers and Phase D review helpers (no engine, no model file)."""

import numpy as np
import pandas as pd

from ep_model.phase_c.evaluate import fit_logistic_1d, lichess_expected
from ep_model.phase_c.prepare import FEATURE_NAMES, add_model_features, apply_clock_dropout
from ep_model.phase_d.review import best_move_row, label_for_loss


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
    assert label_for_loss(0.15, False) == "blunder"


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
