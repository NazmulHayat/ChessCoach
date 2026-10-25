"""
Parity fixture for the in-browser review: full Python reviews of benchmark games, with the cached engine fields
each review used, so web/src/review/review.test.ts can replay the TypeScript port on identical inputs.

Usage (repo root, after `python -m ep_model.benchmark.run precompute`):
  python -m ep_model.scripts.export_web_reviews
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ep_model.benchmark.run import CachedEvals, game_fens, load_sets, puzzle_game, read_game
from ep_model.phase_d.predictor import EPModel, board_model_dir, default_model_dir
from ep_model.phase_d.review import review_game

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "web" / "src" / "review" / "__fixtures__" / "reviews.json"
KEEP_MOVE = ["ply", "san", "uci", "mover", "best_uci", "best_san", "best_line_san", "second_san", "ep_best", "ep_after", "ep_loss",
             "ep_second", "ep_label", "base_label", "lichess_label", "lichess_loss", "accuracy", "phase", "tactic", "sacrifice",
             "sacrifice_piece", "capture", "clock_sec", "weight", "cp_before"]


def main() -> int:
    sets = load_sets()
    evals = CachedEvals(17)
    board, chances = EPModel(board_model_dir()), EPModel(default_model_dir())
    games = []
    for tc in ("bullet", "blitz", "rapid"):
        games += [(f"lichess {g['id']}", g["pgn"], True) for g in sets["lichess"] if g["time_class"] == tc][:8]
    cc = [g for g in sets["chesscom"] if all(f in evals.data for f in game_fens(read_game(g["pgn"])))]
    games += [(f"chesscom {g['id']}", g["pgn"], True) for g in cc[:8]]
    games += [(f"case {c['name']} #{i}", c["pgn"], False) for i, c in enumerate(sets["cases"][::4])]
    out = []
    for name, pgn, use_book in games:
        game = read_game(pgn)
        fens = game_fens(game)
        kw = {} if use_book else {"book_path": None}
        r = review_game(game, board, lambda f, p: evals(f, p), 17, chances_model=chances, **kw)
        out.append(
            {
                "name": name,
                "pgn": pgn,
                "use_book": use_book,
                "engine": {f: evals.data[f] for f in fens},
                "expected": {
                    "white_elo": r["white_elo"], "black_elo": r["black_elo"], "time_class": r["time_class"],
                    "rating_pool": r["rating_pool"], "rating_band": r["rating_band"],
                    "white_ep_by_ply": r["white_ep_by_ply"], "white_lichess_by_ply": r["white_lichess_by_ply"],
                    "moves": [{k: m[k] for k in KEEP_MOVE} for m in r["moves"]],
                    "summary": r["summary"], "key_moments": r["key_moments"],
                },
            }
        )
    for p in sets["puzzles"][:10]:
        game = puzzle_game(p)
        r = review_game(game, board, lambda f, pr: evals(f, pr), 17, book_path=None, chances_model=chances)
        out.append({"name": f"puzzle {p['PuzzleId']}", "pgn": str(game), "use_book": False,
                    "engine": {f: evals.data[f] for f in game_fens(game)},
                    "expected": {"moves": [{k: m[k] for k in KEEP_MOVE} for m in r["moves"]], "summary": r["summary"],
                                 "white_ep_by_ply": r["white_ep_by_ply"], "key_moments": r["key_moments"]}})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out), encoding="utf-8")
    print(f"{OUT.relative_to(REPO)}: {len(out)} reviews, {OUT.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
