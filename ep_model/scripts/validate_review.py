"""
Independent checks of the review, against references we didn't produce.

  lichess  Games Lichess's servers analysed (deeper engine; its verdicts are in the PGN as ?! ? ?? glyphs).
           Do we flag the same errors? Also: label stability on a second run, and the game rating estimate
           on the real app path.
  accuracy Our copy of Lichess's accuracy formula vs the accuracy Lichess itself shows, on real analysed
           games from the public API (same engine evals in, so the numbers should match).
  compare  Same Lichess-analysed games through two judging models (default: board-only vs clock-aware), split
           by time class: agreement with Lichess's verdicts, error counts per player, and game accuracy vs
           Lichess's accuracy formula on Lichess's own evals.
  puzzles  Lichess puzzles: each starts with a real blunder and has one winning answer. We should call the
           blunder an error, the answer best / great, and the tactic hint should match the puzzle theme.

Usage (repo root):
  python -m ep_model.scripts.validate_review puzzles --n 300
  python -m ep_model.scripts.validate_review lichess --games 100 --repeat 20
  python -m ep_model.scripts.validate_review compare --per-class 50
Reports go to ep_model/models/validation_*.json (and are printed).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import random
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import chess
import chess.pgn

from ep_model.phase_a.generate_rows import stream_games
from ep_model.phase_a.rowgen import classify_time_class, parse_time_control
from ep_model.phase_d.accuracy import lichess_game_accuracy
from ep_model.phase_d.engine_pool import EnginePool
from ep_model.phase_d.predictor import EPModel, board_model_dir
from ep_model.phase_d.review import review_game

LOG = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "ep_model" / "models"
PUZZLE_URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"

ERRORS = {"inaccuracy", "mistake", "miss", "blunder"}
SERIOUS = {"mistake", "miss", "blunder"}
GOOD = {"brilliant", "great", "best", "excellent"}
# PGN NAG codes Lichess writes: ?! = 6, ? = 2, ?? = 4.
NAG_LABEL = {6: "inaccuracy", 2: "mistake", 4: "blunder"}


def pct(a: int, b: int) -> float | None:
    return round(100.0 * a / b, 1) if b else None


def make_reviewer(workers: int, depth: int, model: EPModel | None = None):
    model = model or EPModel(board_model_dir())
    pool = EnginePool(workers=workers)

    def run(game: chess.pgn.Game, judge: EPModel | None = None, **kw):
        return review_game(game, judge or model, lambda fens, prog: pool.analyse(fens, depth, prog), depth, **kw)

    return run, pool


# ---------- puzzles ----------


def load_puzzles(path: Path, n: int, seed: int) -> list[dict]:
    if not path.is_file():
        LOG.info("Downloading the first 60k puzzles from %s", PUZZLE_URL)
        path.parent.mkdir(parents=True, exist_ok=True)
        cmd = f"curl -sL {PUZZLE_URL} | zstd -dc 2>/dev/null | head -n 60001 > '{path}'"
        subprocess.run(["sh", "-c", cmd], check=False)
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    random.Random(seed).shuffle(rows)
    return rows[:n]


def puzzle_game(p: dict) -> chess.pgn.Game:
    board = chess.Board(p["FEN"])
    game = chess.pgn.Game()
    game.setup(board)
    game.headers.update({"WhiteElo": "1500", "BlackElo": "1500", "TimeControl": "300+0", "Site": "lichess puzzle"})
    node = game
    for u in p["Moves"].split():
        node = node.add_variation(chess.Move.from_uci(u))
    return game


def run_puzzles(args) -> dict:
    puzzles = load_puzzles(args.puzzle_file, args.n, args.seed)
    review, pool = make_reviewer(args.workers, args.depth)
    setup, first, solver = Counter(), Counter(), Counter()
    alive = alive_flagged = 0  # setup moves where the mover still had >= 15% chances
    mate_total = mate_hint = mate_exact = hang_total = hang_hint = 0
    misses: dict[str, list] = {"setup_not_flagged": [], "mate_hint_missing": [], "solution_not_good": []}
    t0 = time.time()
    try:
        for k, p in enumerate(puzzles):
            r = review(puzzle_game(p), book_path=None)
            moves = r["moves"]
            setup[moves[0]["ep_label"]] += 1
            if moves[0]["ep_best"] >= 0.15:
                alive += 1
                alive_flagged += moves[0]["ep_label"] in ERRORS
            first[moves[1]["ep_label"]] += 1
            for m in moves[1::2]:
                solver[m["ep_label"]] += 1
            themes = p["Themes"].split()
            hint = moves[0]["tactic"] or ""
            mates = [t for t in themes if t.startswith("mateIn")]
            if mates:
                mate_total += 1
                mate_hint += "allows mate" in hint
                mate_exact += hint == f"allows mate in {mates[0][len('mateIn'):]}"
                if "allows mate" not in hint:
                    misses["mate_hint_missing"].append([p["PuzzleId"], mates[0], moves[0]["ep_label"], hint, round(moves[0]["ep_best"], 3)])
            if moves[0]["ep_label"] not in ERRORS:
                misses["setup_not_flagged"].append([p["PuzzleId"], moves[0]["ep_label"], round(moves[0]["ep_best"], 3), round(moves[0]["ep_after"], 3)])
            for m in moves[1::2]:
                if m["ep_label"] not in GOOD:
                    misses["solution_not_good"].append([p["PuzzleId"], m["ply"], m["san"], m["ep_label"], m["best_san"], round(m["ep_loss"], 3)])
            if "hangingPiece" in themes:
                hang_total += 1
                hang_hint += hint.startswith("hangs")
            if (k + 1) % 50 == 0:
                LOG.info("%d/%d puzzles, %.0fs", k + 1, len(puzzles), time.time() - t0)
    finally:
        pool.close()
    ns, nf, nv = sum(setup.values()), sum(first.values()), sum(solver.values())
    return {
        "puzzles": len(puzzles),
        "depth": args.depth,
        "seconds": round(time.time() - t0, 1),
        "setup_move_flagged_any_error_pct": pct(sum(setup[l] for l in ERRORS), ns),
        "setup_move_flagged_mistake_or_worse_pct": pct(sum(setup[l] for l in SERIOUS), ns),
        "setup_move_labels": dict(setup.most_common()),
        "setup_moves_not_already_lost": alive,
        "setup_move_flagged_when_not_already_lost_pct": pct(alive_flagged, alive),
        "first_solution_move_good_pct": pct(sum(first[l] for l in GOOD), nf),
        "first_solution_move_best_great_brilliant_pct": pct(first["best"] + first["great"] + first["brilliant"], nf),
        "first_solution_move_great_or_brilliant_pct": pct(first["great"] + first["brilliant"], nf),
        "first_solution_move_labels": dict(first.most_common()),
        "all_solution_moves_good_pct": pct(sum(solver[l] for l in GOOD), nv),
        "mate_puzzles": mate_total,
        "mate_hint_pct": pct(mate_hint, mate_total),
        "mate_hint_exact_n_pct": pct(mate_exact, mate_total),
        "hanging_piece_puzzles": hang_total,
        "hanging_piece_hint_pct": pct(hang_hint, hang_total),
        "examples": {k: v[:15] for k, v in misses.items()},
        "counts": {k: len(v) for k, v in misses.items()},
    }


# ---------- Lichess-analysed games ----------


def sample_analysed_games(path: Path, n: int, keep_prob: float, seed: int) -> list[chess.pgn.Game]:
    rng = random.Random(seed)
    out = []
    for game in stream_games(path):
        h = game.headers
        if h.get("TimeControl", "-") == "-" or not h.get("WhiteElo", "").isdigit() or not h.get("BlackElo", "").isdigit():
            continue
        if rng.random() > keep_prob:
            continue
        nodes = list(game.mainline())
        if len(nodes) < 20 or "%eval" not in (nodes[0].comment or ""):
            continue
        out.append(game)
        if len(out) >= n:
            break
    return out


def confusion(pairs: list[tuple[str, str]]) -> dict:
    """pairs of (lichess verdict, our label) for moves Lichess rated."""
    lich_blunders = [o for l, o in pairs if l == "blunder"]
    lich_serious = [o for l, o in pairs if l in ("mistake", "blunder")]
    lich_clean = [o for l, o in pairs if l == "none"]
    ours_blunder = [l for l, o in pairs if o == "blunder"]
    ours_serious = [l for l, o in pairs if o in SERIOUS]
    return {
        "lichess_blunders": len(lich_blunders),
        "we_flag_lichess_blunders_as_mistake_or_worse_pct": pct(sum(o in SERIOUS for o in lich_blunders), len(lich_blunders)),
        "we_flag_lichess_blunders_as_any_error_pct": pct(sum(o in ERRORS for o in lich_blunders), len(lich_blunders)),
        "we_flag_lichess_mistakes_or_blunders_as_any_error_pct": pct(sum(o in ERRORS for o in lich_serious), len(lich_serious)),
        "our_blunders": len(ours_blunder),
        "lichess_also_flags_our_blunders_pct": pct(sum(l != "none" for l in ours_blunder), len(ours_blunder)),
        "lichess_calls_our_blunders_mistake_or_blunder_pct": pct(sum(l in ("mistake", "blunder") for l in ours_blunder), len(ours_blunder)),
        "lichess_also_flags_our_mistakes_or_worse_pct": pct(sum(l != "none" for l in ours_serious), len(ours_serious)),
        "lichess_clean_moves": len(lich_clean),
        "we_flag_lichess_clean_moves_as_mistake_or_worse_pct": pct(sum(o in SERIOUS for o in lich_clean), len(lich_clean)),
    }


def run_lichess(args) -> dict:
    games = sample_analysed_games(args.dump, args.games, args.keep_prob, args.seed)
    LOG.info("Sampled %d Lichess-analysed games", len(games))
    review, pool = make_reviewer(args.workers, args.depth)
    ep_pairs, evalonly_pairs = [], []
    est_err, base_err, est_pairs = [], [], []
    first_labels: dict[int, list[str]] = {}
    t0 = time.time()
    try:
        for gi, game in enumerate(games):
            r = review(game)
            nags = [node.nags for node in game.mainline()]
            for m, ns in zip(r["moves"], nags):
                if m["ep_label"] == "book":
                    continue
                verdict = next((NAG_LABEL[n] for n in ns if n in NAG_LABEL), "none")
                ep_pairs.append((verdict, m["ep_label"]))
                evalonly_pairs.append((verdict, m["lichess_label"]))
            for side in ("white", "black"):
                est = r["summary"][side]["estimated_rating"]
                if est:
                    est_pairs.append((est["rating"], r[f"{side}_elo"]))
            if gi < args.repeat:
                first_labels[gi] = [m["ep_label"] for m in r["moves"]]
            if (gi + 1) % 10 == 0:
                LOG.info("%d/%d games, %.0fs", gi + 1, len(games), time.time() - t0)
    finally:
        pool.close()

    # Stability: same games again with fresh engines (empty hash and cache).
    review2, pool2 = make_reviewer(args.workers, args.depth)
    same = total = 0
    try:
        for gi in sorted(first_labels):
            again = [m["ep_label"] for m in review2(games[gi])["moves"]]
            same += sum(a == b for a, b in zip(first_labels[gi], again))
            total += len(again)
    finally:
        pool2.close()

    truth = [t for _, t in est_pairs]
    median = statistics.median(truth) if truth else 0
    est_err = [abs(e - t) for e, t in est_pairs]
    base_err = [abs(median - t) for t in truth]
    corr = None
    if len(est_pairs) > 2:
        xs, ys = zip(*est_pairs)
        mx, my = statistics.mean(xs), statistics.mean(ys)
        num = sum((x - mx) * (y - my) for x, y in est_pairs)
        den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
        corr = round(num / den, 3) if den else None
    return {
        "games": len(games),
        "moves_compared": len(ep_pairs),
        "depth": args.depth,
        "seconds": round(time.time() - t0, 1),
        "lichess_verdicts": dict(Counter(l for l, _ in ep_pairs).most_common()),
        "ep_labels_vs_lichess": confusion(ep_pairs),
        "eval_only_labels_vs_lichess": confusion(evalonly_pairs),
        "stability_games": len(first_labels),
        "stability_same_label_pct": pct(same, total),
        "rating_estimate": {
            "players": len(est_pairs),
            "mae": round(statistics.mean(est_err), 1) if est_err else None,
            "mae_guess_median": round(statistics.mean(base_err), 1) if base_err else None,
            "corr": corr,
        },
    }


def sample_by_time_class(path: Path, per_class: int, keep_prob: float, seed: int) -> dict[str, list[chess.pgn.Game]]:
    """Lichess-analysed games, `per_class` each of bullet / blitz / rapid."""
    rng = random.Random(seed)
    out: dict[str, list[chess.pgn.Game]] = {"bullet": [], "blitz": [], "rapid": []}
    for game in stream_games(path):
        h = game.headers
        if h.get("TimeControl", "-") == "-" or not h.get("WhiteElo", "").isdigit() or not h.get("BlackElo", "").isdigit():
            continue
        tc = classify_time_class(parse_time_control(h["TimeControl"])[0])
        if tc not in out or len(out[tc]) >= per_class or rng.random() > keep_prob:
            continue
        nodes = list(game.mainline())
        if len(nodes) < 20 or "%eval" not in (nodes[0].comment or ""):
            continue
        out[tc].append(game)
        if all(len(v) >= per_class for v in out.values()):
            break
    return out


def run_compare(args) -> dict:
    models = {"board": EPModel(board_model_dir()), "clock": EPModel(Path(args.other_model) if args.other_model else None)}
    by_tc = sample_by_time_class(args.dump, args.per_class, args.keep_prob, args.seed)
    LOG.info("Sampled %s", {k: len(v) for k, v in by_tc.items()})
    review, pool = make_reviewer(args.workers, args.depth, models["board"])
    report: dict = {"depth": args.depth, "games": {k: len(v) for k, v in by_tc.items()}}
    t0 = time.time()
    try:
        for tc, games in by_tc.items():
            pairs = {name: [] for name in models}
            counts = {name: Counter() for name in models}
            acc_diff = {name: [] for name in models}
            li_counts: Counter = Counter()
            players = 0
            for gi, game in enumerate(games):
                nags = [node.nags for node in game.mainline()]
                cps = _cps_from_pgn(str(game))
                li_acc = lichess_game_accuracy(cps) if cps else None
                for side in ("white", "black"):
                    players += 1
                    for k, ns in enumerate(nags):
                        if (k % 2 == 0) == (side == "white"):
                            v = next((NAG_LABEL[n] for n in ns if n in NAG_LABEL), None)
                            if v:
                                li_counts[v] += 1
                for name, model in models.items():
                    r = review(game, judge=model)  # engine evals are cached after the first model
                    for m, ns in zip(r["moves"], nags):
                        if m["ep_label"] != "book":
                            pairs[name].append((next((NAG_LABEL[n] for n in ns if n in NAG_LABEL), "none"), m["ep_label"]))
                        if m["ep_label"] in ERRORS:
                            counts[name][m["ep_label"]] += 1
                    if li_acc:
                        for side in ("white", "black"):
                            if li_acc[side] is not None:
                                acc_diff[name].append(r["summary"][side]["accuracy"] - li_acc[side])
                if (gi + 1) % 10 == 0:
                    LOG.info("%s %d/%d, %.0fs", tc, gi + 1, len(games), time.time() - t0)
            report[tc] = {
                "lichess_errors_per_player": {k: round(v / players, 2) for k, v in sorted(li_counts.items())},
                **{
                    name: {
                        "errors_per_player": {k: round(v / players, 2) for k, v in sorted(counts[name].items())},
                        "accuracy_mean_diff_vs_lichess": round(statistics.mean(acc_diff[name]), 2) if acc_diff[name] else None,
                        "accuracy_mean_abs_diff_vs_lichess": round(statistics.mean(map(abs, acc_diff[name])), 2) if acc_diff[name] else None,
                        **confusion(pairs[name]),
                    }
                    for name in models
                },
            }
    finally:
        pool.close()
    report["seconds"] = round(time.time() - t0, 1)
    return report


# ---------- accuracy formula vs Lichess ----------

LICHESS_HEADERS = {"Accept": "application/x-ndjson", "User-Agent": "ChessCoach/0.1 (accuracy validation)"}


def _cps_from_pgn(pgn: str) -> list[float] | None:
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        return None
    cps = [15.0]  # Lichess's eval of the start position
    nodes = list(game.mainline())
    for k, node in enumerate(nodes):
        ev = node.eval()
        if ev is None:
            if k == len(nodes) - 1 and node.board().is_checkmate():
                cps.append(1000.0 if node.board().turn == chess.BLACK else -1000.0)
                continue
            if k == len(nodes) - 1:
                break  # Lichess doesn't evaluate a final position after resign/timeout either
            return None
        cps.append(float(ev.white().score(mate_score=100_000)))
    return cps if len(cps) > 10 else None


def run_accuracy(args) -> dict:
    import httpx

    users: list[str] = []
    for game in stream_games(args.dump):
        for side in ("White", "Black"):
            name = game.headers.get(side)
            if name and name not in users and random.Random(name).random() < 0.3:
                users.append(name)
        if len(users) >= args.users:
            break
    diffs: list[float] = []
    rows = []
    with httpx.Client(headers=LICHESS_HEADERS, timeout=30) as client:
        for u in users:
            r = client.get(
                f"https://lichess.org/api/games/user/{u}",
                params={"max": args.per_user, "analysed": "true", "accuracy": "true", "evals": "true", "pgnInJson": "true", "clocks": "false"},
            )
            time.sleep(1.0)
            if r.status_code != 200:
                LOG.info("%s: HTTP %s", u, r.status_code)
                continue
            for line in r.text.splitlines():
                g = json.loads(line)
                if g.get("variant") != "standard" or g.get("initialFen"):
                    continue
                cps = _cps_from_pgn(g.get("pgn", ""))
                if cps is None:
                    continue
                ours = lichess_game_accuracy(cps)
                for side in ("white", "black"):
                    theirs = (g["players"][side].get("analysis") or {}).get("accuracy")
                    if theirs is None or ours[side] is None:
                        continue
                    diffs.append(ours[side] - theirs)
                    rows.append([g["id"], side, theirs, round(ours[side], 2)])
    absd = [abs(d) for d in diffs]
    return {
        "users": len(users),
        "player_games": len(diffs),
        "mean_abs_diff": round(statistics.mean(absd), 3) if absd else None,
        "within_0_5_pct": pct(sum(d <= 0.5 for d in absd), len(absd)),
        "within_1_pct": pct(sum(d <= 1.0 for d in absd), len(absd)),
        "max_abs_diff": round(max(absd), 2) if absd else None,
        "examples_worst": sorted(rows, key=lambda r: -abs(r[3] - r[2]))[:10],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    pz = sub.add_parser("puzzles")
    pz.add_argument("--n", type=int, default=300)
    pz.add_argument("--puzzle-file", type=Path, default=REPO / "ep_model" / "raw" / "puzzles_head.csv")
    ac = sub.add_parser("accuracy")
    ac.add_argument("--users", type=int, default=20)
    ac.add_argument("--per-user", type=int, default=10)
    ac.add_argument("--dump", type=Path, default=REPO / "ep_model" / "raw" / "lichess_db_standard_rated_2026-02.pgn.zst")
    li = sub.add_parser("lichess")
    li.add_argument("--games", type=int, default=100)
    li.add_argument("--repeat", type=int, default=20, help="Re-review this many games to measure stability")
    li.add_argument("--keep-prob", type=float, default=0.05)
    li.add_argument("--dump", type=Path, default=REPO / "ep_model" / "raw" / "lichess_db_standard_rated_2026-02.pgn.zst")
    cp_ = sub.add_parser("compare")
    cp_.add_argument("--per-class", type=int, default=50, help="Games per time class (bullet, blitz, rapid)")
    cp_.add_argument("--keep-prob", type=float, default=0.05)
    cp_.add_argument("--other-model", default=None, help="Model dir to compare against (default: the clock-aware app model)")
    cp_.add_argument("--dump", type=Path, default=REPO / "ep_model" / "raw" / "lichess_db_standard_rated_2026-02.pgn.zst")
    for s in (pz, li, ac, cp_):
        s.add_argument("--depth", type=int, default=17)
        s.add_argument("--workers", type=int, default=8)
        s.add_argument("--seed", type=int, default=11)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = {"puzzles": run_puzzles, "lichess": run_lichess, "accuracy": run_accuracy, "compare": run_compare}[args.cmd](args)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"validation_{args.cmd}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
