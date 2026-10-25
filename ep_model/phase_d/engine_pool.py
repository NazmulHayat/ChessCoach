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


class EnginePool:
    """
    `workers` Stockfish processes, one per thread. analyse() keeps input order and caches results by
    (FEN, depth) so re-reviewing a game, or shared opening positions, cost nothing.
    """

    def __init__(
        self,
        stockfish_path: str = "stockfish",
        workers: int = 4,
        threads: int = 1,
        hash_mb: int = 64,
        cache_size: int = 50_000,
    ):
        self.workers = max(1, workers)
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
        board = chess.Board(fen)
        eng = self._engines.get()
        try:
            info = eng.analyse(board, chess.engine.Limit(depth=depth))
        finally:
            self._engines.put(eng)
        pv = info.get("pv") or []
        return {**extract_eval_fields(board, info), "best_uci": pv[0].uci() if pv else None}

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
