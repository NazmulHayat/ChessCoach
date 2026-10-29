"""Phase B continuous queue: output order, FEN dedupe and cache use, with a fake engine (no Stockfish)."""

import random
import time

import chess
import chess.engine
import pyarrow as pa
import pyarrow.parquet as pq

from ep_model.sampling.generate_rows import PARQUET_SCHEMA
from ep_model.labeling import augment_evals


class FakeEngine:
    calls: list[str] = []

    def configure(self, _opts):
        pass

    def analyse(self, board, _limit, multipv=1):
        FakeEngine.calls.append(board.fen())
        time.sleep(random.uniform(0, 0.01))  # out-of-order completion
        score = chess.engine.PovScore(chess.engine.Cp(len(board.fen()) % 97), board.turn)
        return [{"score": score, "depth": 1}]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _rows(n_games=12, plies=6):
    rows = []
    for g in range(n_games):
        board = chess.Board()
        for ply in range(1, plies + 1):
            mv = list(board.legal_moves)[(g + ply) % board.legal_moves.count()]
            rows.append({name: None for name in PARQUET_SCHEMA.names} | {
                "game_id": f"g{g}", "ply": ply, "fen": board.fen(), "side_to_move": "w" if board.turn else "b",
            })
            board.push(mv)
    return rows


def test_queue_keeps_order_dedupes_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(chess.engine.SimpleEngine, "popen_uci", staticmethod(lambda _path: FakeEngine()))
    FakeEngine.calls = []
    rows = _rows()
    inp = tmp_path / "in"
    inp.mkdir()
    pq.write_table(pa.Table.from_pylist(rows, schema=PARQUET_SCHEMA), inp / "rows_no_eval_part00001.parquet")
    policy = tmp_path / "policy.json"
    policy.write_text('{"stockfish_path": "fake", "depth": 1, "threads": 1, "hash_mb": 16}')

    def run(out):
        return augment_evals.run(inp, tmp_path / out, policy, tmp_path / "cache.sqlite", tmp_path / f"ck_{out}.sqlite",
                                 max_rows=None, flush_rows=20, resume=False, workers=4)

    assert run("out1") == 0
    out = pq.read_table(sorted((tmp_path / "out1").glob("*.parquet"))).to_pylist()
    assert [(r["game_id"], r["ply"]) for r in out] == [(r["game_id"], r["ply"]) for r in rows]
    unique = {r["fen"] for r in rows}
    assert len(unique) < len(rows)  # every game starts from the same position
    assert sorted(FakeEngine.calls) == sorted(unique)  # one engine call per distinct FEN
    assert all(r["eval_cp_stm"] == len(r["fen"]) % 97 for r in out)

    FakeEngine.calls = []
    assert run("out2") == 0  # second run: everything from the FEN cache
    assert FakeEngine.calls == []
