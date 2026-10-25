"""
Phase B: read Phase A Parquet shards, run Stockfish per FEN (with cache), write rows_with_eval_*.parquet.

Usage (repo root, Stockfish on PATH):
  python -m ep_model.phase_b.augment_evals --max-rows 2500 -v

See ep_model/config/engine_policy.json for depth/threads (fixed for reproducibility).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import queue
import re
import sqlite3
import sys
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

import chess
import chess.engine
import pyarrow as pa
import pyarrow.parquet as pq

from ep_model.phase_a.generate_rows import PARQUET_SCHEMA
from ep_model.phase_b.eval_extract import extract_eval_fields

LOG = logging.getLogger(__name__)

PART_OUT_RE = re.compile(r"rows_with_eval_part(\d+)\.parquet$")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_policy_path() -> Path:
    return _repo_root() / "ep_model" / "config" / "engine_policy.json"


def load_policy(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_output_schema() -> pa.Schema:
    extra = [
        pa.field("eval_cp_white", pa.int32(), nullable=True),
        pa.field("mate_white", pa.int32(), nullable=True),
        pa.field("eval_cp_stm", pa.int32(), nullable=True),
        pa.field("mate_stm", pa.int32(), nullable=True),
        pa.field("eval_depth", pa.int32(), nullable=True),
    ]
    return pa.schema(list(PARQUET_SCHEMA) + extra)


OUTPUT_SCHEMA = build_output_schema()


def open_fen_cache(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fen_cache (
            fen TEXT PRIMARY KEY,
            eval_cp_white INTEGER,
            mate_white INTEGER,
            eval_cp_stm INTEGER,
            mate_stm INTEGER,
            eval_depth INTEGER
        )
        """
    )
    conn.commit()
    return conn


def cache_get(conn: sqlite3.Connection, fen: str) -> dict | None:
    cur = conn.execute(
        "SELECT eval_cp_white, mate_white, eval_cp_stm, mate_stm, eval_depth FROM fen_cache WHERE fen = ?",
        (fen,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "eval_cp_white": row[0],
        "mate_white": row[1],
        "eval_cp_stm": row[2],
        "mate_stm": row[3],
        "eval_depth": row[4],
    }


def cache_put(conn: sqlite3.Connection, fen: str, fields: dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO fen_cache
        (fen, eval_cp_white, mate_white, eval_cp_stm, mate_stm, eval_depth)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            fen,
            fields["eval_cp_white"],
            fields["mate_white"],
            fields["eval_cp_stm"],
            fields["mate_stm"],
            fields["eval_depth"],
        ),
    )


def open_row_checkpoint(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS row_done (game_id TEXT NOT NULL, ply INTEGER NOT NULL, PRIMARY KEY (game_id, ply))"
    )
    conn.commit()
    return conn


def is_row_done(conn: sqlite3.Connection, game_id: str, ply: int) -> bool:
    cur = conn.execute("SELECT 1 FROM row_done WHERE game_id = ? AND ply = ?", (game_id, ply))
    return cur.fetchone() is not None


def mark_rows_done(conn: sqlite3.Connection, keys: list[tuple[str, int]]) -> None:
    conn.executemany("INSERT OR IGNORE INTO row_done (game_id, ply) VALUES (?, ?)", keys)
    conn.commit()


def next_output_shard_index(out_dir: Path) -> int:
    m = 0
    for p in out_dir.glob("rows_with_eval_part*.parquet"):
        match = PART_OUT_RE.search(p.name)
        if match:
            m = max(m, int(match.group(1)))
    return m + 1


def run(
    input_dir: Path,
    out_dir: Path,
    policy_path: Path,
    cache_path: Path,
    row_ck_path: Path,
    max_rows: int | None,
    flush_rows: int,
    resume: bool,
    summary_json: Path | None = None,
    workers: int = 1,
) -> int:
    policy = load_policy(policy_path)
    stockfish_path = policy.get("stockfish_path", "stockfish")
    depth = int(policy["depth"])
    threads = int(policy["threads"])
    hash_mb = int(policy["hash_mb"])
    multipv = int(policy.get("multipv", 1))

    inputs = sorted(input_dir.glob("rows_no_eval_part*.parquet"))
    if not inputs:
        LOG.error("No rows_no_eval_part*.parquet in %s", input_dir)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    fen_conn = open_fen_cache(cache_path)
    row_conn = open_row_checkpoint(row_ck_path)
    if not resume:
        row_conn.execute("DELETE FROM row_done")
        row_conn.commit()

    stats = {
        "rows_out": 0,
        "rows_skipped_done": 0,
        "cache_hits": 0,
        "engine_calls": 0,
        "t_engine": 0.0,
    }

    buffer: list[dict] = []
    shard_idx = next_output_shard_index(out_dir)
    t0 = time.perf_counter()

    limit_reached = False
    workers = max(1, workers)
    # Continuous queue: each uncached FEN is submitted as soon as its row is read, and rows leave a
    # sliding window in input order once their eval is ready. Only a full window blocks (on its oldest
    # row), so engines stay busy instead of idling at the end of a chunk while its slowest position
    # finishes. Cache lookups, cache writes and output stay on this thread, in input order.
    window_size = 32 * workers

    def flush() -> None:
        nonlocal shard_idx
        out_path = out_dir / f"rows_with_eval_part{shard_idx:05d}.parquet"
        pq.write_table(
            pa.Table.from_pylist(buffer, schema=OUTPUT_SCHEMA),
            out_path,
            compression="zstd",
        )
        keys = [(r["game_id"], int(r["ply"])) for r in buffer]
        mark_rows_done(row_conn, keys)
        LOG.info("Wrote %s (%s rows)", out_path.name, len(buffer))
        buffer.clear()
        shard_idx += 1

    try:
        with contextlib.ExitStack() as stack, ThreadPoolExecutor(max_workers=workers) as pool:
            engines: queue.Queue = queue.Queue()
            for _ in range(workers):
                eng = stack.enter_context(chess.engine.SimpleEngine.popen_uci(stockfish_path))
                eng.configure({"Threads": threads, "Hash": hash_mb})
                engines.put(eng)
            limit_obj = chess.engine.Limit(depth=depth)

            def analyse(fen: str) -> tuple[dict, float]:
                board = chess.Board(fen)
                eng = engines.get()
                try:
                    t_e0 = time.perf_counter()
                    raw_info = eng.analyse(board, limit_obj, multipv=multipv)
                    dt = time.perf_counter() - t_e0
                finally:
                    engines.put(eng)
                info = raw_info[0] if isinstance(raw_info, list) else raw_info
                return extract_eval_fields(board, info), dt

            window: deque[dict] = deque()  # rows read but not yet written, in input order
            ready: dict[str, dict] = {}  # fen -> eval fields, while rows in the window still need them
            inflight: dict[str, Future] = {}  # fen -> engine job
            refs: dict[str, int] = {}  # fen -> rows in the window with this fen
            since_commit = 0

            def admit(row: dict) -> None:
                fen = row["fen"]
                window.append(row)
                refs[fen] = refs.get(fen, 0) + 1
                if fen in ready or fen in inflight:
                    return
                cached = cache_get(fen_conn, fen)
                if cached is not None:
                    stats["cache_hits"] += 1
                    ready[fen] = cached
                else:
                    inflight[fen] = pool.submit(analyse, fen)

            def emit_head(block: bool) -> bool:
                """Write the oldest row if its eval is ready (waiting for it if `block`)."""
                nonlocal since_commit
                row = window[0]
                fen = row["fen"]
                if fen not in ready:
                    fut = inflight[fen]
                    if not block and not fut.done():
                        return False
                    fields, dt = fut.result()
                    del inflight[fen]
                    stats["engine_calls"] += 1
                    stats["t_engine"] += dt
                    cache_put(fen_conn, fen, fields)
                    since_commit += 1
                    if since_commit >= 256:
                        fen_conn.commit()
                        since_commit = 0
                    ready[fen] = fields
                window.popleft()
                buffer.append({**row, **ready[fen]})
                refs[fen] -= 1
                if refs[fen] == 0:
                    del refs[fen], ready[fen]
                stats["rows_out"] += 1
                if len(buffer) >= flush_rows:
                    fen_conn.commit()
                    flush()
                return True

            for ipath in inputs:
                if limit_reached:
                    break
                LOG.info("Input %s", ipath.name)
                pf = pq.ParquetFile(ipath)
                for rg in range(pf.num_row_groups):
                    if limit_reached:
                        break
                    tbl = pf.read_row_group(rg)
                    for batch in tbl.to_batches(max_chunksize=256):
                        if limit_reached:
                            break
                        for row in batch.to_pylist():
                            if max_rows is not None and stats["rows_out"] + len(window) >= max_rows:
                                limit_reached = True
                                break
                            if resume and is_row_done(row_conn, row["game_id"], int(row["ply"])):
                                stats["rows_skipped_done"] += 1
                                continue
                            admit(row)
                            while window and emit_head(block=len(window) >= window_size):
                                pass
            while window:
                emit_head(block=True)
            fen_conn.commit()

        if buffer:
            flush()

    except chess.engine.EngineTerminatedError as e:
        LOG.error("Stockfish failed (%s). Is `%s` on PATH?", e, stockfish_path)
        return 1
    finally:
        fen_conn.close()
        row_conn.close()

    elapsed = time.perf_counter() - t0
    ec = stats["engine_calls"] or 1
    avg_e = stats["t_engine"] / ec
    LOG.info(
        "Phase B done: rows_written=%s skipped_done=%s cache_hits=%s engine_calls=%s elapsed=%.1fs avg_engine_call=%.3fs",
        stats["rows_out"],
        stats["rows_skipped_done"],
        stats["cache_hits"],
        stats["engine_calls"],
        elapsed,
        avg_e,
    )
    if stats["engine_calls"] > 0:
        extrap = (
            f"Rough extrapolation: 1M new engine positions ≈ "
            f"{stats['t_engine'] / stats['engine_calls'] * 1e6 / 3600:.1f} engine-hours at this policy "
            f"(÷ {workers} workers for wall time)."
        )
        LOG.info(extrap)

    if summary_json is not None:
        _write_summary(
            summary_json,
            policy_path,
            stats,
            elapsed,
            limit_reached,
            max_rows,
        )
    return 0


def _write_summary(
    path: Path,
    policy_path: Path,
    stats: dict[str, Any],
    elapsed: float,
    limit_reached: bool,
    max_rows: int | None,
) -> None:
    """Machine-readable summary for orchestrators (safe_run, CI)."""
    ec = int(stats["engine_calls"])
    avg_e = (stats["t_engine"] / ec) if ec else 0.0
    skipped = int(stats["rows_skipped_done"])
    written = int(stats["rows_out"])
    # Full scan: every row was already in checkpoint — nothing left to augment for current Phase A shards.
    no_pending_work = written == 0 and skipped > 0
    summary: dict[str, Any] = {
        "rows_written": written,
        "rows_skipped_done": skipped,
        "cache_hits": int(stats["cache_hits"]),
        "engine_calls": ec,
        "elapsed_sec": round(elapsed, 3),
        "avg_engine_call_sec": round(avg_e, 6),
        "batch_limit_hit": limit_reached,
        "max_rows": max_rows,
        "no_pending_work": no_pending_work,
        "policy_path": str(policy_path),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    proc = root / "ep_model" / "processed"
    p = argparse.ArgumentParser(description="Phase B: add Stockfish evals to Phase A Parquet")
    p.add_argument("--input-dir", type=Path, default=proc)
    p.add_argument("--out-dir", type=Path, default=proc)
    p.add_argument("--policy", type=Path, default=default_policy_path())
    p.add_argument(
        "--cache-db",
        type=Path,
        default=proc / "fen_eval_cache.sqlite",
        help="SQLite FEN → eval cache (persists across runs)",
    )
    p.add_argument(
        "--checkpoint-db",
        type=Path,
        default=proc / "phase_b_row_checkpoint.sqlite",
        help="SQLite (game_id, ply) already written to output",
    )
    p.add_argument("--max-rows", type=int, default=None, help="Stop after N new output rows (pilot)")
    p.add_argument("--flush-rows", type=int, default=10_000, help="Rows per output Parquet shard")
    p.add_argument("--resume", action="store_true", help="Skip (game_id,ply) in checkpoint DB")
    p.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel Stockfish processes (each uses the policy's threads / hash)",
    )
    p.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Write run stats JSON (default: ep_model/processed/phase_b_last_summary.json)",
    )
    p.add_argument(
        "--no-summary-json",
        action="store_true",
        help="Do not write phase_b_last_summary.json",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Less logging (use --summary-json for progress; meant for safe_run wrapper)",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    if args.verbose and args.quiet:
        LOG.error("Use either -v or --quiet, not both")
        return 1

    log_level = logging.DEBUG if args.verbose else (logging.WARNING if args.quiet else logging.INFO)
    logging.basicConfig(level=log_level, format="%(levelname)s %(message)s")

    if not args.policy.is_file():
        LOG.error("Missing policy file: %s", args.policy)
        return 1

    summary_path: Path | None = None
    if not args.no_summary_json:
        summary_path = args.summary_json if args.summary_json is not None else proc / "phase_b_last_summary.json"

    return run(
        input_dir=args.input_dir,
        out_dir=args.out_dir,
        policy_path=args.policy,
        cache_path=args.cache_db,
        row_ck_path=args.checkpoint_db,
        max_rows=args.max_rows,
        flush_rows=args.flush_rows,
        resume=args.resume,
        summary_json=summary_path,
        workers=args.workers,
    )


if __name__ == "__main__":
    sys.exit(main())
