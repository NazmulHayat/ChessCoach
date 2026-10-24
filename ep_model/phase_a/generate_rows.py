"""
Stream Lichess .pgn.zst dumps, sample half-move rows (Phase A), write Parquet shards.

Usage (from repo root):
  python -m ep_model.phase_a.generate_rows --max-games 500 --plies-per-game 5

Requires: pip install -r ep_model/requirements-ep.txt
"""

from __future__ import annotations

import argparse
import logging
import random
import re
import sqlite3
import sys
import time
from pathlib import Path

import chess.pgn
import pyarrow as pa
import pyarrow.parquet as pq
import zstandard

from ep_model.phase_a.rowgen import build_game_meta, extract_rows_for_game

LOG = logging.getLogger(__name__)

PARQUET_SCHEMA = pa.schema(
    [
        ("game_id", pa.string()),
        ("ply", pa.int32()),
        ("move_number", pa.int32()),
        ("side_to_move", pa.string()),
        ("fen", pa.string()),
        ("played_move_uci", pa.string()),
        ("white_elo", pa.int32()),
        ("black_elo", pa.int32()),
        ("elo_to_move", pa.int32()),
        ("elo_opponent", pa.int32()),
        ("elo_diff", pa.int32()),
        ("time_class", pa.string()),
        ("initial_time_sec", pa.int32()),
        ("increment_sec", pa.int32()),
        ("clk_white_sec", pa.float64()),
        ("clk_black_sec", pa.float64()),
        ("phase", pa.string()),
        ("opening_eco", pa.string()),
        ("result_white", pa.float64()),
        ("result_stm", pa.float64()),
        ("rating_band", pa.string()),
        ("stratum_key", pa.string()),
    ]
)

PART_RE = re.compile(r"rows_no_eval_part(\d+)\.parquet$")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_paths() -> tuple[Path, Path, Path]:
    root = _repo_root()
    raw = root / "ep_model" / "raw"
    out = root / "ep_model" / "processed"
    ck = out / "phase_a_checkpoint.sqlite"
    return raw, out, ck


def next_shard_index(out_dir: Path) -> int:
    m = 0
    for p in out_dir.glob("rows_no_eval_part*.parquet"):
        match = PART_RE.search(p.name)
        if match:
            m = max(m, int(match.group(1)))
    return m + 1


def rows_to_table(rows: list[dict]) -> pa.Table:
    if not rows:
        raise ValueError("empty rows")
    return pa.Table.from_pylist(rows, schema=PARQUET_SCHEMA)


def open_checkpoint(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE IF NOT EXISTS processed_games (game_id TEXT PRIMARY KEY)")
    conn.commit()
    return conn


def is_processed(conn: sqlite3.Connection, game_id: str) -> bool:
    cur = conn.execute("SELECT 1 FROM processed_games WHERE game_id = ?", (game_id,))
    return cur.fetchone() is not None


def mark_processed(conn: sqlite3.Connection, game_id: str) -> None:
    conn.execute("INSERT OR IGNORE INTO processed_games (game_id) VALUES (?)", (game_id,))
    conn.commit()


def stream_games(path: Path):
    """Yield chess.pgn.Game from a .pgn.zst file."""
    with zstandard.open(path, "rt") as f:
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            yield game


def run(
    raw_dir: Path,
    out_dir: Path,
    checkpoint_path: Path,
    plies_per_game: int,
    seed: int,
    shard_rows: int,
    max_games: int | None,
    resume: bool,
) -> int:
    files = sorted(raw_dir.glob("*.pgn.zst"))
    if not files:
        LOG.error("No .pgn.zst files in %s", raw_dir)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    conn = open_checkpoint(checkpoint_path)
    if not resume:
        conn.execute("DELETE FROM processed_games")
        conn.commit()
    rng = random.Random(seed)

    processed_count = 0
    buffer: list[dict] = []
    shard_idx = next_shard_index(out_dir)
    t0 = time.perf_counter()

    for zst_path in files:
        LOG.info("Reading %s", zst_path)
        try:
            for game in stream_games(zst_path):
                if max_games is not None and processed_count >= max_games:
                    break

                meta = build_game_meta(game)
                if meta is None:
                    continue

                if resume and is_processed(conn, meta.game_id):
                    continue

                try:
                    rows = extract_rows_for_game(game, meta, rng, plies_per_game)
                except Exception as e:
                    LOG.exception("Failed game %s: %s", meta.game_id, e)
                    raise

                if not rows:
                    mark_processed(conn, meta.game_id)
                    processed_count += 1
                    continue

                buffer.extend(rows)
                mark_processed(conn, meta.game_id)
                processed_count += 1

                while len(buffer) >= shard_rows:
                    chunk = buffer[:shard_rows]
                    del buffer[:shard_rows]
                    out_path = out_dir / f"rows_no_eval_part{shard_idx:05d}.parquet"
                    table = rows_to_table(chunk)
                    pq.write_table(table, out_path, compression="zstd")
                    LOG.info("Wrote %s (%s rows)", out_path.name, len(chunk))
                    shard_idx += 1

            if max_games is not None and processed_count >= max_games:
                break
        except FileNotFoundError:
            LOG.error("Missing file: %s", zst_path)
            return 1

    if buffer:
        out_path = out_dir / f"rows_no_eval_part{shard_idx:05d}.parquet"
        table = rows_to_table(buffer)
        pq.write_table(table, out_path, compression="zstd")
        LOG.info("Wrote %s (%s rows)", out_path.name, len(buffer))

    elapsed = time.perf_counter() - t0
    LOG.info("Done: %s games processed in %.1fs", processed_count, elapsed)
    conn.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    raw_d, out_d, ck_d = _default_paths()
    p = argparse.ArgumentParser(description="Phase A: PGN.zst → Parquet rows (no eval)")
    p.add_argument("--raw-dir", type=Path, default=raw_d)
    p.add_argument("--out-dir", type=Path, default=out_d)
    p.add_argument("--checkpoint", type=Path, default=ck_d)
    p.add_argument("--plies-per-game", type=int, default=5)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--shard-rows", type=int, default=50_000)
    p.add_argument("--max-games", type=int, default=None)
    p.add_argument("--resume", action="store_true", help="Skip games in checkpoint DB")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    if args.plies_per_game < 1:
        LOG.error("--plies-per-game must be >= 1")
        return 1

    return run(
        raw_dir=args.raw_dir,
        out_dir=args.out_dir,
        checkpoint_path=args.checkpoint,
        plies_per_game=args.plies_per_game,
        seed=args.seed,
        shard_rows=args.shard_rows,
        max_games=args.max_games,
        resume=args.resume,
    )


if __name__ == "__main__":
    sys.exit(main())
