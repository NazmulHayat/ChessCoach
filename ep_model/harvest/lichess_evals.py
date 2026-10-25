"""
Harvest training rows from Lichess's own server analysis instead of running Stockfish.

About 1 in 10 games in a Lichess monthly dump was analysed on Lichess (fishnet, Stockfish) and
carries `{ [%eval 0.17] [%clk 0:01:00] }` after every move. Those evals are free engine labels:
this reads them straight from the movetext (no board replay, no engine) and writes rows in the
same shape as Phase B output, sampling K positions per game like Phase A.

Games already used in the Phase A/B set are skipped, so that set stays a clean held-out test set.

Usage (repo root):
  python -m ep_model.harvest.lichess_evals --max-games 20000          # pilot
  python -m ep_model.harvest.lichess_evals                            # whole dump
"""

from __future__ import annotations

import argparse
import logging
import multiprocessing as mp
import random
import re
import sys
import threading
import time
import zlib
from pathlib import Path
from typing import Any, Iterator

import pyarrow as pa
import pyarrow.parquet as pq
import zstandard

from ep_model.phase_a.rowgen import (
    classify_time_class,
    extract_game_id,
    game_phase_from_half_moves,
    parse_clock_token,
    parse_result_header,
    parse_time_control,
    rating_band_from_average,
)
from ep_model.phase_b.augment_evals import OUTPUT_SCHEMA

LOG = logging.getLogger(__name__)

HEADER_RE = re.compile(r'^\[(\w+) "([^"]*)"\]', re.M)
# "12. Nf3 { ... }" or "12... Nf6 { ... }" (annotation glyphs like ?! are part of the SAN token)
MOVE_RE = re.compile(r"(\d+)(\.\.\.|\.)\s+\S+\s+\{([^}]*)\}")
# Any numbered move, with or without a comment (the final move often has none).
MOVENUM_RE = re.compile(r"(\d+)(\.\.\.|\.)\s+[^\s{}]+")
EVAL_RE = re.compile(r"\[%eval\s+(#?)(-?[\d.]+)\]")
CLK_RE = re.compile(r"\[%clk\s+([^\]]+)\]")

CHUNK_BYTES = 32 * 1024 * 1024
GAME_SEP = b"\n\n[Event "


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def parse_eval(comment: str) -> tuple[int | None, int | None] | None:
    """(cp_white, mate_white) from a movetext comment, or None if it has no eval."""
    m = EVAL_RE.search(comment)
    if not m:
        return None
    if m.group(1) == "#":
        return None, int(m.group(2))
    return int(round(float(m.group(2)) * 100)), None


def rows_for_game(text: str, k_plies: int, exclude: frozenset[str]) -> list[dict[str, Any]]:
    """Sample up to k positions (before a move) whose eval is known from the previous move's comment."""
    split = text.find("\n\n")
    if split == -1:
        return []
    head, moves_text = text[:split], text[split + 2 :]
    h = dict(HEADER_RE.findall(head))
    game_id = extract_game_id(h.get("Site", ""))
    if game_id in exclude:
        return []
    try:
        white_elo, black_elo = int(h["WhiteElo"]), int(h["BlackElo"])
    except (KeyError, ValueError):
        return []
    result_white, _ = parse_result_header(h.get("Result"))
    if result_white is None:
        return []
    init, inc = parse_time_control(h.get("TimeControl"))
    time_class = classify_time_class(init)
    band = rating_band_from_average((white_elo + black_elo) / 2.0)
    eco = h.get("ECO") or None

    # Per half-move index: eval after that move (white POV) and the mover's clock after it.
    evals: dict[int, tuple[int | None, int | None]] = {}
    clocks: dict[int, float] = {}
    n_half = 0
    for m in MOVE_RE.finditer(moves_text):
        idx = (int(m.group(1)) - 1) * 2 + (0 if m.group(2) == "." else 1)
        comment = m.group(3)
        ev = parse_eval(comment)
        if ev is not None:
            evals[idx] = ev
        c = CLK_RE.search(comment)
        if c:
            sec = parse_clock_token(c.group(1).strip())
            if sec is not None:
                clocks[idx] = sec
        n_half = max(n_half, idx + 1)
    last = None
    for last in MOVENUM_RE.finditer(moves_text):
        pass
    if last is not None:
        n_half = max(n_half, (int(last.group(1)) - 1) * 2 + (0 if last.group(2) == "." else 1) + 1)

    # Position before half-move i has the eval written after half-move i-1.
    candidates = [i for i in range(1, n_half) if (i - 1) in evals]
    if not candidates:
        return []
    rng = random.Random(zlib.crc32(game_id.encode()))
    picked = sorted(rng.sample(candidates, k=min(k_plies, len(candidates))))

    rows = []
    for i in picked:
        white_to_move = i % 2 == 0
        cp_w, mate_w = evals[i - 1]
        sign = 1 if white_to_move else -1
        # Latest clock of each side at or before half-move i-1 (white moves are even indices).
        clk_w = next((clocks[j] for j in range(i - 1, -1, -1) if j % 2 == 0 and j in clocks), None)
        clk_b = next((clocks[j] for j in range(i - 1, -1, -1) if j % 2 == 1 and j in clocks), None)
        elo_to_move, elo_opp = (white_elo, black_elo) if white_to_move else (black_elo, white_elo)
        rows.append(
            {
                "game_id": game_id,
                "ply": i + 1,
                "move_number": i // 2 + 1,
                "side_to_move": "w" if white_to_move else "b",
                "fen": None,
                "played_move_uci": None,
                "white_elo": white_elo,
                "black_elo": black_elo,
                "elo_to_move": elo_to_move,
                "elo_opponent": elo_opp,
                "elo_diff": elo_to_move - elo_opp,
                "time_class": time_class,
                "initial_time_sec": init,
                "increment_sec": inc,
                "clk_white_sec": clk_w,
                "clk_black_sec": clk_b,
                "phase": game_phase_from_half_moves(i),
                "opening_eco": eco,
                "result_white": result_white,
                "result_stm": result_white if white_to_move else 1.0 - result_white,
                "rating_band": band,
                "stratum_key": f"{band}_{time_class}",
                "eval_cp_white": cp_w,
                "mate_white": mate_w,
                "eval_cp_stm": sign * cp_w if cp_w is not None else None,
                "mate_stm": sign * mate_w if mate_w is not None else None,
                "eval_depth": None,
            }
        )
    return rows


# --- worker side -------------------------------------------------------------------------------

_EXCLUDE: frozenset[str] = frozenset()
_K = 5


def _init_worker(exclude: frozenset[str], k: int) -> None:
    global _EXCLUDE, _K
    _EXCLUDE, _K = exclude, k


def process_chunk(chunk: bytes) -> tuple[int, int, list[dict[str, Any]]]:
    """(games seen, games with evals, rows) for one block of whole games."""
    games = chunk.count(b"[Event ")
    rows: list[dict[str, Any]] = []
    eval_games = 0
    for raw in chunk.split(GAME_SEP):
        if b"%eval" not in raw:
            continue
        eval_games += 1
        text = raw.decode("utf-8", errors="replace")
        if not text.startswith("[Event "):
            text = "[Event " + text
        rows.extend(rows_for_game(text, _K, _EXCLUDE))
    return games, eval_games, rows


# --- main side ---------------------------------------------------------------------------------


def iter_chunks(path: Path, slots: threading.Semaphore) -> Iterator[bytes]:
    """Blocks of whole games from the .zst stream. `slots` bounds how many are in flight."""
    with open(path, "rb") as f:
        reader = zstandard.ZstdDecompressor().stream_reader(f, read_size=4 * 1024 * 1024)
        carry = b""
        while True:
            data = reader.read(CHUNK_BYTES)
            if not data:
                break
            buf = carry + data
            cut = buf.rfind(GAME_SEP)
            if cut <= 0:
                carry = buf
                continue
            carry = buf[cut + 2 :]
            slots.acquire()
            yield buf[:cut]
        if carry.strip():
            slots.acquire()
            yield carry


def load_exclude_ids(processed: Path) -> frozenset[str]:
    ids: set[str] = set()
    for p in sorted(processed.glob("rows_no_eval_part*.parquet")) + sorted(processed.glob("rows_with_eval_part*.parquet")):
        ids.update(pq.read_table(p, columns=["game_id"]).column("game_id").to_pylist())
    return frozenset(ids)


def run(
    dump: Path,
    out_dir: Path,
    exclude: frozenset[str],
    k_plies: int,
    workers: int,
    shard_rows: int,
    max_games: int | None,
) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("rows_lichess_part*.parquet"):
        old.unlink()

    slots = threading.Semaphore(workers * 3)
    buffer: list[dict[str, Any]] = []
    shard = 0
    seen = eval_games = rows_total = 0
    t0 = time.perf_counter()
    last_log = t0

    def flush() -> None:
        nonlocal shard
        pq.write_table(pa.Table.from_pylist(buffer, schema=OUTPUT_SCHEMA), out_dir / f"rows_lichess_part{shard:05d}.parquet", compression="zstd")
        shard += 1
        buffer.clear()

    with mp.Pool(workers, initializer=_init_worker, initargs=(exclude, k_plies)) as pool:
        for g, eg, rows in pool.imap_unordered(process_chunk, iter_chunks(dump, slots)):
            slots.release()
            seen += g
            eval_games += eg
            rows_total += len(rows)
            buffer.extend(rows)
            if len(buffer) >= shard_rows:
                flush()
            now = time.perf_counter()
            if now - last_log > 30:
                last_log = now
                LOG.info("%.1fM games read | %.2fM with evals | %.1fM rows | %.0fs", seen / 1e6, eval_games / 1e6, rows_total / 1e6, now - t0)
            if max_games is not None and eval_games >= max_games:
                pool.terminate()
                break
    if buffer:
        flush()
    LOG.info(
        "Done: %s games read, %s with evals, %s rows in %s shard(s), %.0fs -> %s",
        seen, eval_games, rows_total, shard, time.perf_counter() - t0, out_dir,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    p = argparse.ArgumentParser(description="Harvest EP training rows from Lichess [%eval] annotations")
    p.add_argument("--dump", type=Path, default=None, help="Lichess .pgn.zst (default: first file in ep_model/raw/)")
    p.add_argument("--out-dir", type=Path, default=root / "ep_model" / "processed_lichess")
    p.add_argument("--exclude-dir", type=Path, default=root / "ep_model" / "processed", help="Skip game_ids found in Phase A/B Parquet here")
    p.add_argument("--plies-per-game", type=int, default=5)
    p.add_argument("--workers", type=int, default=max(1, mp.cpu_count() - 1))
    p.add_argument("--shard-rows", type=int, default=1_000_000)
    p.add_argument("--max-games", type=int, default=None, help="Stop after this many eval-annotated games (pilot)")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    dump = args.dump or next(iter(sorted((root / "ep_model" / "raw").glob("*.pgn.zst"))), None)
    if dump is None or not dump.exists():
        LOG.error("No dump found; pass --dump")
        return 1
    exclude = load_exclude_ids(args.exclude_dir)
    LOG.info("Excluding %s Phase A/B games (held-out test set)", len(exclude))
    return run(dump, args.out_dir, exclude, args.plies_per_game, args.workers, args.shard_rows, args.max_games)


if __name__ == "__main__":
    sys.exit(main())
