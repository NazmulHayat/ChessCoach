"""Unit tests for EP Phase A row generation (no .pgn.zst required)."""

import io
import random

import chess.pgn

from ep_model.phase_a import rowgen
from ep_model.phase_a.generate_rows import PARQUET_SCHEMA, rows_to_table


MINI_PGN = """[Event "Test"]
[Site "https://lichess.org/abcdefgh"]
[Date "2024.01.01"]
[White "A"]
[Black "B"]
[Result "1-0"]
[WhiteElo "1500"]
[BlackElo "1600"]
[TimeControl "300+0"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 *
"""


def test_parse_time_control():
    assert rowgen.parse_time_control("300+0") == (300, 0)
    assert rowgen.parse_time_control("180+2") == (180, 2)
    assert rowgen.parse_time_control("600") == (600, 0)


def test_result_stm():
    assert rowgen.result_stm(1.0, True) == 1.0
    assert rowgen.result_stm(1.0, False) == 0.0
    assert rowgen.result_stm(0.5, False) == 0.5


def test_extract_game_id():
    assert rowgen.extract_game_id("https://lichess.org/abc123") == "abc123"


def test_extract_rows_for_game_sample():
    game = chess.pgn.read_game(io.StringIO(MINI_PGN))
    rng = random.Random(0)
    rows = rowgen.extract_rows_for_game_fixed(game, rng, k_plies=2)
    assert len(rows) == 2
    fens = {r["fen"] for r in rows}
    assert len(fens) == 2
    for r in rows:
        assert r["game_id"] == "abcdefgh"
        assert r["result_white"] == 1.0
        assert r["white_elo"] == 1500
        assert r["black_elo"] == 1600
        assert r["time_class"] == "blitz"


def test_rows_to_table_roundtrip():
    game = chess.pgn.read_game(io.StringIO(MINI_PGN))
    rng = random.Random(1)
    rows = rowgen.extract_rows_for_game_fixed(game, rng, k_plies=1)
    assert len(rows) == 1
    table = rows_to_table(rows)
    assert table.schema.names == list(PARQUET_SCHEMA.names)
