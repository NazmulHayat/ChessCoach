"""Phase B eval field extraction; optional Stockfish integration test."""

import chess
import chess.engine
import pytest

from ep_model.phase_b.eval_extract import extract_eval_fields


def test_extract_starting_position_with_stockfish():
    try:
        with chess.engine.SimpleEngine.popen_uci("stockfish") as engine:
            board = chess.Board()
            raw = engine.analyse(board, chess.engine.Limit(depth=8), multipv=1)
            info = raw[0] if isinstance(raw, list) else raw
            fields = extract_eval_fields(board, info)
    except (chess.engine.EngineTerminatedError, FileNotFoundError, OSError):
        pytest.skip("stockfish not available on PATH")

    assert fields["eval_depth"] is not None
    assert fields["eval_depth"] >= 1
    # start position: usually not mate
    if fields["mate_white"] is None:
        assert fields["eval_cp_white"] is not None
    if fields["mate_stm"] is None:
        assert fields["eval_cp_stm"] is not None
