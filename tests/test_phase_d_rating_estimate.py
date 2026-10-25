"""Game rating features, phase detection and phase grades (no engine, no model)."""

import chess
import pytest

from ep_model.phase_d.rating_estimate import features, move_accuracy, phase_grade, phase_of, win_prob
from ep_model.phase_d.ratings import from_lichess_scale, to_lichess_scale


def test_features():
    f = features([0.0, 0.0, 0.25, 0.15], [20, 2000, 500, 100], "rapid")
    acc, blunders, mistakes, inacc, precise, log_n, mean_cp, bal_acc, bal_share, tc = f
    assert acc == pytest.approx((100 + 100 + move_accuracy(0.25) + move_accuracy(0.15)) / 4)
    assert (blunders, mistakes, inacc, precise) == (0.25, 0.25, 0.0, 0.5)
    assert log_n == pytest.approx(1.3862943611)
    assert mean_cp == pytest.approx((20 + 1000 + 500 + 100) / 4)  # |eval| clipped at 1000
    assert bal_acc == pytest.approx((100 + move_accuracy(0.15)) / 2) and bal_share == 0.5
    assert tc == 2.0


def test_win_prob_is_clipped_and_symmetric():
    assert win_prob(0) == pytest.approx(0.5)
    assert win_prob(300) + win_prob(-300) == pytest.approx(1.0)
    assert win_prob(5000) == win_prob(1000)


def test_phases():
    start = chess.Board()
    assert phase_of(start, 1, in_book=True) == "opening"
    assert phase_of(start, 30, in_book=True) == "opening"  # still in book
    assert phase_of(start, 30, in_book=False) == "middlegame"
    # Rook + bishop each side + two knights = 6 pieces: endgame, even early.
    end = chess.Board("2r1k3/8/2b5/8/8/2B2N2/5N2/2R1K3 w - - 0 30")
    assert phase_of(end, 10, in_book=False) == "endgame"


def test_phase_grade():
    assert phase_grade([]) is None
    book = [{"accuracy": 100.0, "ep_label": "book"}] * 3
    assert phase_grade(book)["grade"] == "book"
    g = phase_grade([{"accuracy": 90.0, "ep_label": "excellent"}, {"accuracy": 80.0, "ep_label": "good"}])
    assert g["accuracy"] == 85.0 and g["grade"] == "excellent" and g["moves"] == 2
    assert phase_grade([{"accuracy": 10.0, "ep_label": "blunder"}])["grade"] == "blunder"


def test_rating_pool_inverse():
    for elo in (800, 1500, 2200):
        back = from_lichess_scale(to_lichess_scale(elo, "chesscom", "blitz"), "chesscom", "blitz")
        assert abs(back - elo) <= 10
    assert from_lichess_scale(1500, "lichess", "blitz") == 1500
