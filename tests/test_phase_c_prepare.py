"""Phase C split and feature helpers."""

import numpy as np
import pandas as pd
import pytest

from ep_model.phase_c.prepare import (
    cp_or_mate_proxy,
    mate_to_pseudo_cp,
    metrics_regression,
    split_by_game_id,
    split_game_ids,
)


def test_mate_to_pseudo_cp():
    assert mate_to_pseudo_cp(3) == 10000 - 300
    assert mate_to_pseudo_cp(-2) == -(10000 - 200)


def test_cp_or_mate_proxy():
    assert cp_or_mate_proxy(50, None) == 50.0
    assert cp_or_mate_proxy(None, 1) == 9900.0


def test_split_game_ids_matches_split_by_game_id():
    df = pd.DataFrame(
        {
            "game_id": ["a", "a", "b", "b", "c", "c"],
            "x": range(6),
        }
    )
    tr_a, va_a = split_by_game_id(df, val_fraction=0.34, seed=0)
    tg, vg = split_game_ids(df["game_id"].unique(), 0.34, 0)
    assert set(tr_a["game_id"].unique()) == tg
    assert set(va_a["game_id"].unique()) == vg


def test_split_by_game_id_no_overlap():
    df = pd.DataFrame(
        {
            "game_id": ["a", "a", "b", "b", "c", "c"],
            "x": range(6),
        }
    )
    tr, va = split_by_game_id(df, val_fraction=0.34, seed=0)
    g_tr = set(tr["game_id"].unique())
    g_va = set(va["game_id"].unique())
    assert g_tr.isdisjoint(g_va)
    assert g_tr | g_va == {"a", "b", "c"}


def test_split_by_game_id_raises_one_game():
    df = pd.DataFrame({"game_id": ["a", "a"], "x": [1, 2]})
    with pytest.raises(ValueError, match="at least 2"):
        split_by_game_id(df, 0.2, 0)


def test_metrics_regression():
    y = np.array([0.0, 0.5, 1.0])
    p = np.array([0.1, 0.4, 0.9])
    m = metrics_regression(y, p)
    assert "mae" in m and "brier_clipped" in m
