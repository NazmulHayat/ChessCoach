"""
Review a random sample of games from the Lichess dump with the full app pipeline and report how often
each label fires, overall and by rating band. Used to sanity-check the Great / Miss / Brilliant rules.

Usage (repo root):
  python -m ep_model.scripts.label_stats --games 200 --workers 8 --out ep_model/models/label_stats.json
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import chess.pgn

from ep_model.sampling.generate_rows import stream_games
from ep_model.review.engine_pool import EnginePool
from ep_model.review.predictor import EPModel, board_model_dir
from ep_model.review.review import review_game

LOG = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parents[2]
BANDS = [(0, 1200), (1200, 1600), (1600, 2000), (2000, 4000)]


def band_name(elo: int) -> str:
    for lo, hi in BANDS:
        if lo <= elo < hi:
            return f"{lo}-{hi}" if hi < 4000 else f"{lo}+"
    return "?"


def sample_games(path: Path, n: int, keep_prob: float, seed: int) -> list[chess.pgn.Game]:
    rng = random.Random(seed)
    out = []
    for game in stream_games(path):
        h = game.headers
        if h.get("Variant", "Standard") != "Standard" or h.get("TimeControl", "-") == "-":
            continue
        if not h.get("WhiteElo", "").isdigit() or not h.get("BlackElo", "").isdigit():
            continue
        if rng.random() > keep_prob:
            continue
        if sum(1 for _ in game.mainline_moves()) < 20:
            continue
        out.append(game)
        if len(out) >= n:
            break
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--dump", type=Path, default=REPO / "ep_model" / "raw" / "lichess_db_standard_rated_2026-02.pgn.zst")
    p.add_argument("--games", type=int, default=200)
    p.add_argument("--keep-prob", type=float, default=0.02, help="Sample this fraction of eligible games")
    p.add_argument("--depth", type=int, default=17)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--out", type=Path, default=REPO / "ep_model" / "models" / "label_stats.json")
    p.add_argument("--reviews-out", type=Path, default=None, help="Optional JSONL of per-game summaries")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    games = sample_games(args.dump, args.games, args.keep_prob, args.seed)
    LOG.info("Sampled %d games", len(games))
    model = EPModel(board_model_dir())
    overall: Counter = Counter()
    by_band: dict[str, Counter] = defaultdict(Counter)
    per_game = []
    t0 = time.time()
    with EnginePool(workers=args.workers) as pool:
        for gi, game in enumerate(games):
            r = review_game(game, model, lambda fens, prog: pool.analyse(fens, args.depth, prog), args.depth)
            for m in r["moves"]:
                elo = r["white_elo"] if m["mover"] == "white" else r["black_elo"]
                overall[m["ep_label"]] += 1
                by_band[band_name(elo)][m["ep_label"]] += 1
            per_game.append(
                {
                    "site": r["headers"].get("Site"),
                    "time_class": r["time_class"],
                    "white_elo": r["white_elo"],
                    "black_elo": r["black_elo"],
                    "moves": [
                        [m["mover"][0], round(m["ep_loss"], 4), round(m["lichess_loss"], 4), m["ep_label"], m["ply"]]
                        for m in r["moves"]
                    ],
                }
            )
            if (gi + 1) % 10 == 0:
                LOG.info("%d/%d games, %.0fs", gi + 1, len(games), time.time() - t0)

    total = sum(overall.values())
    report = {
        "games": len(games),
        "moves": total,
        "depth": args.depth,
        "seconds": round(time.time() - t0, 1),
        "overall_pct": {k: round(100 * v / total, 2) for k, v in overall.most_common()},
        "by_band_pct": {
            b: {"moves": sum(c.values()), **{k: round(100 * v / sum(c.values()), 2) for k, v in c.most_common()}}
            for b, c in sorted(by_band.items())
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.reviews_out:
        with open(args.reviews_out, "w", encoding="utf-8") as f:
            for g in per_game:
                f.write(json.dumps(g) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
