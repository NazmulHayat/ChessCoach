"""Game rating, phase detection and phase grades (no engine, no model)."""

import chess
import pytest

from ep_model.review.rating_estimate import MAX_SWING, game_ratings, phase_grade, phase_of, plays_like, win_prob
from ep_model.review.ratings import from_lichess_scale, to_lichess_scale


META = {"curves": {"blitz": {"accuracy": [60.0, 70.0, 80.0, 90.0], "rating": [800.0, 1200.0, 1600.0, 2000.0]}}, "offset": {"blitz": 2.0}, "spread": {"blitz": 600.0}}
MOVES = {"white": 30, "black": 30}


def test_plays_like_inverts_the_accuracy_curve():
    assert plays_like(82.0, "blitz", META) == pytest.approx(1600.0)  # 82 on our scale = 80 on Lichess's
    # Past the ends the curve continues along its edge slope (40 rating points per accuracy point here).
    assert plays_like(52.0, "blitz", META) == pytest.approx(400.0) and plays_like(102.0, "blitz", META) == pytest.approx(2400.0)
    assert plays_like(77.0, "rapid", META) == plays_like(77.0, "blitz", META)  # unknown class falls back to blitz


def test_more_accurate_player_never_gets_the_lower_game_rating():
    # Very different ratings: still ordered by accuracy, since both are anchored on the game average.
    est = game_ratings({"white": 75.0, "black": 74.0}, {"white": 800.0, "black": 2400.0}, MOVES, "blitz", META)
    assert est["white"]["plays_like"] > est["black"]["plays_like"]
    prev = -1.0
    for acc in range(40, 101, 5):
        r = game_ratings({"white": float(acc), "black": 70.0}, {"white": 1500.0, "black": 1500.0}, MOVES, "blitz", META)
        assert r["white"]["plays_like"] > prev
        prev = r["white"]["plays_like"]


def test_game_rating_stays_within_400_of_the_game_average():
    est = game_ratings({"white": 100.0, "black": 0.0}, {"white": 1500.0, "black": 1500.0}, MOVES, "blitz", META)
    assert 1500.0 < est["white"]["plays_like"] < 1500.0 + MAX_SWING
    assert 1500.0 - MAX_SWING < est["black"]["plays_like"] < 1500.0


def test_game_rating_needs_ten_moves():
    est = game_ratings({"white": 90.0, "black": 90.0}, {"white": 1500.0, "black": 1500.0}, {"white": 9, "black": 10}, "blitz", META)
    assert est["white"] is None and est["black"] is not None


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
    # Lichess-style: mean of the (weighted) mean 85 and the harmonic mean 84.71.
    assert g["accuracy"] == pytest.approx((85 + 2 / (1 / 90 + 1 / 80)) / 2) and g["grade"] == "good" and g["moves"] == 2
    assert phase_grade([{"accuracy": 10.0, "ep_label": "blunder"}])["grade"] == "blunder"


def test_rating_pool_inverse():
    for elo in (800, 1500, 2200):
        back = from_lichess_scale(to_lichess_scale(elo, "chesscom", "blitz"), "chesscom", "blitz")
        assert abs(back - elo) <= 10
    assert from_lichess_scale(1500, "lichess", "blitz") == 1500


def test_lichess_accuracy_aggregation():
    from ep_model.review.accuracy import combine, lichess_game_accuracy, move_accuracy_pct

    assert move_accuracy_pct(0) == 100.0 and move_accuracy_pct(-3) == 100.0
    assert 63 < move_accuracy_pct(10) < 65  # +1 uncertainty bonus on the Lichess curve
    # One blunder among accurate moves pulls the game score down much more than a plain average would.
    accs = [100.0] * 19 + [5.0]
    assert sum(accs) / 20 > 95 and combine(accs, [1.0] * 20) < 80
    # A quiet, equal game is near 100 for both sides.
    acc = lichess_game_accuracy([15.0] + [20.0, 10.0] * 15)
    assert acc["white"] > 98 and acc["black"] > 98
