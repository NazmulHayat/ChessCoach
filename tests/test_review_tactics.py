"""Coach tactic hints from mate scores and static exchanges (no engine)."""

import chess

from ep_model.review.tactics import hanging_after, material_won, tactic_hint

# Legal's mate position before 5...Bxd1 (black to move).
LEGAL = "rn1qkbnr/ppp2p1p/3p2p1/4N3/2B1P1b1/2N5/PPPP1PPP/R1BQK2R b KQkq - 0 5"


def test_allows_mate_beats_other_hints():
    assert tactic_hint(LEGAL, "g4d1", "d6e5", None, 2) == "allows mate in 2"


def test_missed_mate():
    # Back-rank mate Re8# is available; white plays a quiet king move.
    fen = "6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1"
    assert tactic_hint(fen, "g1f1", "e1e8", 1, None) == "missed mate in 1"
    # Still mating, just slower: not a miss.
    assert tactic_hint(fen, "g1f1", "e1e8", 1, -3) is None


def test_hangs_piece():
    # White knight on c3 moves to d5 where the e6 pawn takes it for free.
    b = "4k3/8/4p3/8/8/2N5/8/4K3 w - - 0 1"
    assert hanging_after(chess.Board(b), chess.Move.from_uci("c3d5")) == ("knight on d5", 3)
    assert tactic_hint(b, "c3d5", "e1e2", None, None) == "hangs the knight on d5"


def test_missed_material_win():
    # The black queen on d4 is undefended; white plays a king move instead of Nxd4.
    fen = "4k3/8/8/8/3q4/5N2/8/4K3 w - - 0 1"
    assert material_won(chess.Board(fen), chess.Move.from_uci("f3d4")) == ("queen", 9)
    assert tactic_hint(fen, "e1e2", "f3d4", None, None) == "missed Nxd4, winning the queen"
