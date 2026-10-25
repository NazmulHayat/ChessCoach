"""Great / Miss / Brilliant rules and the static-exchange helpers they use (no engine, no model)."""

import chess
import pytest

from ep_model.phase_d.special import (
    is_brilliant,
    is_great,
    is_miss,
    material_given,
    outcome_band,
    sacrifice_points,
    sacrificed_piece,
    see,
    thresholds_for,
)


def test_thresholds_scale_with_rating():
    lo, hi = thresholds_for(800), thresholds_for(2600)
    assert lo.great_gap == pytest.approx(0.10) and hi.great_gap == pytest.approx(0.15)
    assert lo.brilliant_max_loss == pytest.approx(0.03) and hi.brilliant_max_loss == pytest.approx(0.01)
    mid = thresholds_for(1600)
    assert 0.10 < mid.great_gap < 0.15 and 0.01 < mid.brilliant_max_loss < 0.03


def test_outcome_bands():
    assert [outcome_band(x) for x in (0.1, 0.5, 0.9)] == [0, 1, 2]


def test_see_defended_and_undefended():
    # White knight on e5 attacked by the d6 pawn, defended by the d4 pawn: black wins 3 - 1 = 2.
    b = chess.Board("4k3/8/3p4/4N3/3P4/8/8/4K3 b - - 0 1")
    assert see(b, chess.E5) == 2
    # Undefended knight: black wins all 3.
    b = chess.Board("4k3/8/3p4/4N3/8/8/8/4K3 b - - 0 1")
    assert see(b, chess.E5) == 3
    # Pawn attacked by a queen and defended by a pawn: taking loses the queen, so 0.
    b = chess.Board("4k3/8/8/3q4/4P3/5P2/8/4K3 b - - 0 1")
    assert see(b, chess.E4) == 0


def test_see_respects_pins():
    # The d5 pawn attacks the e4 knight but is pinned to the d8 king by the d1 rook.
    assert see(chess.Board("3k4/8/8/3p4/4N3/8/8/3RK3 b - - 0 1"), chess.E4) == 0
    assert see(chess.Board("3k4/8/8/3p4/4N3/8/8/4K3 b - - 0 1"), chess.E4) == 3


def test_bishop_sac_on_f7_gives_two_points():
    # After 1.e4 e5 2.Bc4 Nc6 3.Nf3 d6: Bxf7+ Kxf7 gives up bishop for pawn.
    b = chess.Board("r1bqkbnr/ppp2ppp/2np4/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 4")
    assert material_given(b, chess.Move.from_uci("c4f7")) == 2
    assert sacrifice_points(b, chess.Move.from_uci("c4f7")) == 2
    assert sacrificed_piece(b, chess.Move.from_uci("c4f7")) == "bishop"
    # A quiet developing move gives nothing away.
    assert sacrifice_points(b, chess.Move.from_uci("b1c3")) == 0


def test_left_hanging_counts_only_when_it_could_be_saved():
    # Bishop a7 attacked by the a8 rook; Bxb6 saves it, so Kd2 sacrifices it.
    b = chess.Board("r3k3/B7/1p6/8/8/8/8/4K3 w - - 0 1")
    assert sacrifice_points(b, chess.Move.from_uci("e1d2")) == 3
    # Knight a8 is trapped (b6 and c7 covered, e4 bishop attacks it): every move loses it, so no sacrifice.
    t = chess.Board("N2k4/p7/8/8/4b3/8/8/4K3 w - - 0 1")
    assert material_given(t, chess.Move.from_uci("e1d2")) == 3
    assert sacrifice_points(t, chess.Move.from_uci("e1d2")) == 0


def test_great_only_move():
    assert is_great(True, 0.55, 0.35, 1500, legal_moves=30, is_obvious_capture=False)
    # Gap too small, same band.
    assert not is_great(True, 0.55, 0.50, 1500, 30, False)
    # Not the engine move, or a forced / obvious recapture.
    assert not is_great(False, 0.55, 0.30, 1500, 30, False)
    assert not is_great(True, 0.55, 0.30, 1500, 1, False)
    assert not is_great(True, 0.55, 0.30, 1500, 30, True)
    assert not is_great(True, 1.0, 0.60, 1500, 30, False, gives_mate=True)
    # Band change (equal -> winning vs second-best equal) with a modest gap.
    assert is_great(True, 0.74, 0.66, 2000, 30, False)
    # Same gap of 0.12 is Great at 1200 but not at 2200.
    assert is_great(True, 0.60, 0.48, 1200, 30, False)
    assert not is_great(True, 0.60, 0.48, 2200, 30, False)


def test_miss():
    # Opponent gave away 0.25; I was at 0.40 before, best now 0.65; I play into 0.45 (lost 0.20).
    assert is_miss(False, ep_loss=0.20, ep_after=0.45, opp_prev_loss=0.25, mover_ep_before_gift=0.40)
    # Gave back less than half the gift: not a miss.
    assert not is_miss(False, 0.08, 0.57, 0.25, 0.40)
    # Fell well below where I was before the gift: a real mistake/blunder of my own, not a miss.
    assert not is_miss(False, 0.40, 0.25, 0.25, 0.40)
    # Opponent's move wasn't a mistake.
    assert not is_miss(False, 0.10, 0.45, 0.05, 0.45)
    assert not is_miss(True, 0.0, 0.65, 0.25, 0.40)


def test_brilliant():
    assert is_brilliant(ep_loss=0.0, ep_after=0.62, ep_second=0.55, elo=1500, sac_points=3)
    assert not is_brilliant(0.0, 0.62, 0.55, 1500, sac_points=0)  # no sacrifice
    assert not is_brilliant(0.0, 0.40, 0.30, 1500, 3)  # still worse after
    assert not is_brilliant(0.0, 0.97, 0.95, 1500, 3)  # already completely winning without it
    assert not is_brilliant(0.05, 0.62, 0.55, 1500, 3)  # not near-best
    # 0.025 loss: forgiven at 1000, not at 2200.
    assert is_brilliant(0.025, 0.6, 0.5, 1000, 3)
    assert not is_brilliant(0.025, 0.6, 0.5, 2200, 3)


def test_taking_a_hanging_piece_is_not_great():
    from ep_model.phase_d.special import takes_hanging_material

    b = chess.Board()
    for san in "d4 e5 dxe5 d6 exd6 Bxd6 Bg5".split():
        b.push_san(san)
    assert takes_hanging_material(b, b.parse_san("Qxg5"))
    assert not takes_hanging_material(b, b.parse_san("Nf6"))
