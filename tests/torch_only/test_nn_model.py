"""PyTorch EP model: feature encoding and a save / load / predict round trip."""

import json

import numpy as np
import pandas as pd
import pytest

torch = pytest.importorskip("torch")

from ep_model.training.prepare import CATEGORICAL_FEATURES, FEATURE_NAMES  # noqa: E402
from ep_model.training.train_nn import META_FILE, MODEL_FILE, EPNet, EPNetPredictor, category_codes, numeric_matrix  # noqa: E402


def _frame(n: int = 6) -> pd.DataFrame:
    rng = np.random.RandomState(0)
    df = pd.DataFrame({f: rng.rand(n) * 100 for f in FEATURE_NAMES if f not in CATEGORICAL_FEATURES})
    df["cp_stm_proxy"] = [-9900.0, -150.0, 0.0, 30.0, 150.0, 9900.0][:n]
    df["clk_stm_sec"] = [-1.0, 60.0, 0.0, 5.0, 300.0, -1.0][:n]
    df["clk_stm_frac"] = [-1.0, 0.5, 0.0, 0.1, 1.0, -1.0][:n]
    df["phase"] = "middlegame"
    df["time_class"] = ["bullet", "blitz", "rapid", "blitz", "bullet", "classical"][:n]
    df["rating_band"] = "1600-1800"
    df["opening_eco"] = ["B01", "C20", "?", "B01", "A00", "E99"][:n]
    return df


def test_numeric_matrix_clips_eval_and_flags_missing_clocks():
    x = numeric_matrix(_frame())
    assert np.isfinite(x).all()
    cp_col = [f for f in FEATURE_NAMES if f not in CATEGORICAL_FEATURES].index("cp_stm_proxy")
    assert x[0, cp_col] == -10.0 and x[-1, cp_col] == 10.0
    win = x[:, -1]
    assert win[0] < 0.05 and win[-1] > 0.95 and abs(win[2] - 0.5) < 1e-6


def test_unseen_category_maps_to_zero():
    vocab = {c: ["blitz", "bullet"] if c == "time_class" else [] for c in CATEGORICAL_FEATURES}
    codes = category_codes(_frame(), vocab)
    tc = codes[:, CATEGORICAL_FEATURES.index("time_class")]
    assert tc.tolist() == [2, 1, 0, 1, 2, 0]


def test_predictor_round_trip(tmp_path):
    df = _frame()
    vocab = {c: sorted(df[c].astype(str).unique().tolist()) for c in CATEGORICAL_FEATURES}
    raw = numeric_matrix(df)
    arch = {"emb_dim": 4, "hidden": 8, "layers": 1, "dropout": 0.0}
    net = EPNet(raw.shape[1], [len(vocab[c]) for c in CATEGORICAL_FEATURES], **arch)
    torch.save(net.state_dict(), tmp_path / MODEL_FILE)
    meta = {"vocab": vocab, "num_mean": raw.mean(0).tolist(), "num_std": (raw.std(0) + 1e-6).tolist(), "arch": arch}
    (tmp_path / META_FILE).write_text(json.dumps(meta))
    p = EPNetPredictor(tmp_path).predict(df)
    assert p.shape == (len(df),) and ((p > 0) & (p < 1)).all()
    np.testing.assert_allclose(p, EPNetPredictor(tmp_path).predict(df))
