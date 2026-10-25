"""Lichess [%eval] harvesting: movetext parsing and row semantics (no dump needed)."""

from ep_model.harvest.lichess_evals import parse_eval, rows_for_game

GAME = """[Event "Rated Blitz game"]
[Site "https://lichess.org/abcd1234"]
[Result "0-1"]
[WhiteElo "1500"]
[BlackElo "1600"]
[ECO "C20"]
[TimeControl "180+2"]

1. e4 { [%eval 0.2] [%clk 0:03:00] } 1... e5 { [%eval 0.25] [%clk 0:02:58] } 2. Qh5?! { [%eval -0.4] [%clk 0:02:55] } 2... Nc6 { [%eval -0.3] [%clk 0:02:50] } 3. Bc4 { [%eval #-3] [%clk 0:02:40] } 3... g6 0-1
"""


def test_parse_eval():
    assert parse_eval("[%eval 0.17] [%clk 0:01:00]") == (17, None)
    assert parse_eval("[%eval -1.6]") == (-160, None)
    assert parse_eval("[%eval #-3]") == (None, -3)
    assert parse_eval("[%clk 0:01:00]") is None


def test_rows_use_previous_move_eval_and_clocks():
    rows = {r["ply"]: r for r in rows_for_game(GAME, k_plies=10, exclude=frozenset())}
    # Positions before half-moves 1..5 (plies 2..6); ply 1 has no eval before it.
    assert sorted(rows) == [2, 3, 4, 5, 6]
    r = rows[3]  # before 2. Qh5, white to move, eval written after 1... e5
    assert r["side_to_move"] == "w" and r["eval_cp_white"] == 25 and r["eval_cp_stm"] == 25
    assert r["clk_white_sec"] == 180 and r["clk_black_sec"] == 178
    assert r["result_stm"] == 0.0 and r["elo_to_move"] == 1500 and r["move_number"] == 2
    b = rows[4]  # before 2... Nc6, black to move, eval -0.4 (white POV) = +40 for black
    assert b["side_to_move"] == "b" and b["eval_cp_stm"] == 40 and b["result_stm"] == 1.0
    m = rows[6]  # before 3... g6, mate for black in 3
    assert m["mate_white"] == -3 and m["mate_stm"] == 3 and m["eval_cp_stm"] is None


def test_excluded_and_sampled():
    assert rows_for_game(GAME, 5, frozenset({"abcd1234"})) == []
    a = rows_for_game(GAME, 2, frozenset())
    assert len(a) == 2 and a == rows_for_game(GAME, 2, frozenset())  # deterministic per game
