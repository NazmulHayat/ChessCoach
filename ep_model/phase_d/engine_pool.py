"""A small pool of long-lived Stockfish processes for analysing many positions in parallel."""

from __future__ import annotations

import queue
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

import chess
import chess.engine

from ep_model.phase_b.eval_extract import extract_eval_fields

ProgressFn = Callable[[int, int], None]
PV_LEN = 8


def _empty_second() -> dict[str, Any]:
    return {"second_uci": None, "second_cp_stm": None, "second_mate_stm": None}


def analysis_fields(board: chess.Board, infos: list[dict] | dict) -> dict[str, Any]:
    """Eval fields of the top line, its first moves (pv_uci), and the second line's move + eval."""
    if isinstance(infos, dict):
        infos = [infos]
    top = infos[0]
    pv = top.get("pv") or []
    out: dict[str, Any] = {
        **extract_eval_fields(board, top),
        "best_uci": pv[0].uci() if pv else None,
        "pv_uci": [m.uci() for m in pv[:PV_LEN]],
        **_empty_second(),
    }
    if len(infos) > 1 and infos[1].get("pv"):
        second = extract_eval_fields(board, infos[1])
        out["second_uci"] = infos[1]["pv"][0].uci()
        out["second_cp_stm"] = second["eval_cp_stm"]
        out["second_mate_stm"] = second["mate_stm"]
    return out


class EnginePool:
    """
    `workers` Stockfish processes, one per thread. analyse() keeps input order and caches results by
    (FEN, depth) so re-reviewing a game, or shared opening positions, cost nothing.

    With multipv=2 each result also carries the second-best move and its eval (second_* fields), which
    the Great / Brilliant labels need. The top line's eval fields are the same as with multipv=1.
    """

    def __init__(
        self,
        stockfish_path: str = "stockfish",
        workers: int = 4,
        threads: int = 1,
        hash_mb: int = 64,
        cache_size: int = 50_000,
        multipv: int = 2,
    ):
        self.workers = max(1, workers)
        self.multipv = max(1, multipv)
        self._engines: queue.Queue = queue.Queue()
        self._all: list[chess.engine.SimpleEngine] = []
        for _ in range(self.workers):
            eng = chess.engine.SimpleEngine.popen_uci(stockfish_path)
            eng.configure({"Threads": threads, "Hash": hash_mb})
            self._engines.put(eng)
            self._all.append(eng)
        self._pool = ThreadPoolExecutor(max_workers=self.workers)
        self._cache: OrderedDict[tuple[str, int], dict[str, Any]] = OrderedDict()
        self._cache_size = cache_size
        self._lock = threading.Lock()

    def _analyse_one(self, fen: str, depth: int) -> dict[str, Any]:
        """
        One position from a cleared engine. The fresh `game` object makes python-chess send ucinewgame
        (clears Stockfish's hash and history), so the result depends only on (FEN, depth), not on what this
        engine searched before. Without it a re-review kept the same label on only 78-82% of moves; with it,
        100%, for about 5% more time (22.3 -> 23.6 s per game, 4 engines, depth 17).
        """
        board = chess.Board(fen)
        eng = self._engines.get()
        try:
            infos = eng.analyse(board, chess.engine.Limit(depth=depth), multipv=self.multipv, game=object())
        finally:
            self._engines.put(eng)
        return analysis_fields(board, infos)

    def analyse(self, fens: list[str], depth: int, progress: ProgressFn | None = None) -> list[dict[str, Any]]:
        """Eval fields (+ best_uci) for each FEN, in input order."""
        results: list[dict[str, Any] | None] = [None] * len(fens)
        todo: dict[str, list[int]] = {}
        with self._lock:
            for i, fen in enumerate(fens):
                hit = self._cache.get((fen, depth))
                if hit is not None:
                    self._cache.move_to_end((fen, depth))
                    results[i] = hit
                else:
                    todo.setdefault(fen, []).append(i)

        done = len(fens) - sum(len(v) for v in todo.values())
        if progress:
            progress(done, len(fens))
        futures = {self._pool.submit(self._analyse_one, fen, depth): fen for fen in todo}
        for fut, fen in futures.items():
            fields = fut.result()
            with self._lock:
                self._cache[(fen, depth)] = fields
                if len(self._cache) > self._cache_size:
                    self._cache.popitem(last=False)
            for i in todo[fen]:
                results[i] = fields
                done += 1
            if progress:
                progress(done, len(fens))
        return results  # type: ignore[return-value]

    def analyse_one(self, fen: str, depth: int) -> dict[str, Any]:
        """Single position, through the cache (e.g. a move tried in retry mode)."""
        return self.analyse([fen], depth)[0]

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
        for eng in self._all:
            try:
                eng.quit()
            except chess.engine.EngineError:
                pass

    def __enter__(self) -> "EnginePool":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
