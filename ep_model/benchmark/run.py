"""
The benchmark: one fixed scorecard for the review, run on the frozen sets in ep_model/benchmark/data.

  precompute  Stockfish on every position of every set, once, saved to cache/evals_d<depth>.jsonl. The engine
              is deterministic per position (cleared before each), so scoring a model afterwards takes seconds.
  score       Review every game with each judging model and score it against the references and targets.
              Writes results/<name>.json and docs/benchmark.md.

Usage (repo root):
  python -m ep_model.benchmark.run precompute --workers 10
  python -m ep_model.benchmark.run score --model board=ep_model/models_board --model clock=ep_model/models_finetuned
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import chess
import chess.pgn

from ep_model.phase_d.accuracy import lichess_game_accuracy
from ep_model.phase_d.engine_pool import EnginePool
from ep_model.phase_d.predictor import EPModel
from ep_model.phase_d.review import review_game

LOG = logging.getLogger(__name__)
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA, CACHE, RESULTS = HERE / "data", HERE / "cache", HERE / "results"
DOC = REPO / "docs" / "benchmark.md"
CLASSES = ("bullet", "blitz", "rapid")

ERRORS = {"inaccuracy", "mistake", "miss", "blunder"}
SERIOUS = {"mistake", "miss", "blunder"}
GOOD = {"brilliant", "great", "best", "excellent"}
LICHESS_VERDICT = {"Inaccuracy": "inaccuracy", "Mistake": "mistake", "Blunder": "blunder"}

# (metric key, description, comparison, target). Checked per time class where the metric has one.
TARGETS = [
    ("li_blunder_caught", "Lichess blunders we call mistake or worse", ">=", 90.0),
    ("li_our_blunders_confirmed", "Our blunders that Lichess also flags", ">=", 95.0),
    ("li_clean_false_alarm", "Moves Lichess passes that we call mistake or worse", "<=", 2.0),
    ("li_error_count_ratio", "Our inaccuracies+mistakes+blunders per player / Lichess's", "between", (0.7, 1.3)),
    ("li_accuracy_mae", "Accuracy gap vs Lichess (points)", "<=", 3.0),
    ("cc_accuracy_mae", "Accuracy gap vs Chess.com (points)", "<=", 3.0),
    ("puzzle_solution_good", "Puzzle answers labelled best / great / brilliant / excellent", ">=", 98.0),
    ("puzzle_setup_flagged", "Puzzle blunders flagged (mover not already lost)", ">=", 95.0),
    ("cases_pass", "Known cases with the right label", ">=", 100.0),
]


def pct(a: float, b: float) -> float | None:
    return round(100.0 * a / b, 1) if b else None


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def read_game(pgn: str) -> chess.pgn.Game:
    return chess.pgn.read_game(io.StringIO(pgn))


def puzzle_game(p: dict) -> chess.pgn.Game:
    game = chess.pgn.Game()
    game.setup(chess.Board(p["FEN"]))
    game.headers.update({"WhiteElo": "1500", "BlackElo": "1500", "TimeControl": "300+0", "Site": "lichess puzzle"})
    node = game
    for u in p["Moves"].split():
        node = node.add_variation(chess.Move.from_uci(u))
    return game


def load_sets() -> dict[str, list]:
    with open(DATA / "puzzles.csv", encoding="utf-8") as f:
        puzzles = list(csv.DictReader(f))
    return {
        "lichess": read_jsonl(DATA / "lichess_games.jsonl"),
        "chesscom": read_jsonl(DATA / "chesscom_games.jsonl"),
        "puzzles": puzzles,
        "cases": json.loads((DATA / "cases.json").read_text(encoding="utf-8")) if (DATA / "cases.json").is_file() else [],
    }


def all_games(sets: dict[str, list]) -> list[chess.pgn.Game]:
    games = [read_game(g["pgn"]) for g in sets["lichess"] + sets["chesscom"]]
    games += [puzzle_game(p) for p in sets["puzzles"]]
    games += [read_game(c["pgn"]) for c in sets["cases"]]
    return games


class CachedEvals:
    """FEN -> engine fields, on disk; misses go to Stockfish (if a pool is given) and are appended."""

    def __init__(self, depth: int, pool: EnginePool | None = None):
        self.depth, self.pool = depth, pool
        self.path = CACHE / f"evals_d{depth}.jsonl"
        self.data: dict[str, dict] = {}
        if self.path.is_file():
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:  # a line still being written by a running precompute
                        continue
                    self.data[row.pop("_fen")] = row

    def __call__(self, fens: list[str], progress: Callable | None = None) -> list[dict[str, Any]]:
        missing = list(dict.fromkeys(f for f in fens if f not in self.data))
        if missing:
            if self.pool is None:
                raise RuntimeError(f"{len(missing)} positions not in the eval cache; run precompute first")
            CACHE.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                for fen, fields in zip(missing, self.pool.analyse(missing, self.depth, progress)):
                    self.data[fen] = fields
                    f.write(json.dumps({"_fen": fen, **fields}) + "\n")
        return [self.data[f] for f in fens]


def game_fens(game: chess.pgn.Game) -> list[str]:
    board = game.board()
    fens = [board.fen()]
    for mv in game.mainline_moves():
        board.push(mv)
        fens.append(board.fen())
    return fens


def precompute(depth: int, workers: int) -> None:
    sets = load_sets()
    fens = list(dict.fromkeys(f for g in all_games(sets) for f in game_fens(g)))
    with EnginePool(workers=workers) as pool:
        ev = CachedEvals(depth, pool)
        todo = [f for f in fens if f not in ev.data]
        LOG.info("%d positions, %d to analyse with %d engines", len(fens), len(todo), workers)
        t0 = time.time()
        chunk = 2000  # big enough that engines rarely sit idle waiting for a chunk's slowest position
        for k in range(0, len(todo), chunk):  # chunks, so progress is saved as it goes
            ev(todo[k : k + chunk])
            done = min(k + chunk, len(todo))
            rate = done / (time.time() - t0)
            LOG.info("%d/%d, %.1f pos/s, ~%.0f min left", done, len(todo), rate, (len(todo) - done) / rate / 60)


# ---------- scoring ----------


def auc(pos: list[float], neg: list[float]) -> float | None:
    """P(a random positive scores above a random negative), ties count half."""
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(wins / (len(pos) * len(neg)), 3)


def result_auc(rows: list[tuple[float, float, str | None]]) -> float | None:
    """How well (white value - black value) picks the winner of decisive games."""
    w = [a - b for a, b, win in rows if win == "white"]
    b = [a - b_ for a, b_, win in rows if win == "black"]
    return auc(w, b)


def eval_only_accuracy(r: dict) -> dict[str, float | None]:
    """Lichess's formula on our engine evals (no model): the 'eval-only' accuracy variant."""
    cps = []
    for p in r["positions"]:
        if p["mate"] is None:
            cps.append(float(p["cp"] or 0))
        elif p["mate"] != 0:
            cps.append(1000.0 if p["mate"] > 0 else -1000.0)
        else:  # checkmate on the board: the side to move lost
            cps.append(-1000.0 if p["fen"].split()[1] == "w" else 1000.0)
    return lichess_game_accuracy(cps, white_starts=r["positions"][0]["fen"].split()[1] == "w")


def score_model(model: EPModel, sets: dict[str, list], evals: CachedEvals, depth: int) -> dict[str, Any]:
    def review(game: chess.pgn.Game, **kw) -> dict:
        return review_game(game, model, lambda fens, prog: evals(fens, prog), depth, **kw)

    out: dict[str, Any] = {"lichess": {}, "chesscom": {}}

    # Lichess: verdicts per move, accuracy per player.
    for tc in CLASSES + ("all",) if sets["lichess"] else ():
        games = [g for g in sets["lichess"] if tc in ("all", g["time_class"])]
        caught = blunders = ours_b = ours_b_conf = clean = clean_flag = 0
        our_err = li_err = 0
        acc_d, acc_eo_d, res_ours, res_li, res_eo, res_pl = [], [], [], [], [], []
        pl_err = []
        for g in games:
            r = review(read_game(g["pgn"]))
            for m, j in zip(r["moves"], g["judgments"]):
                if m["ep_label"] == "book":
                    continue
                v = LICHESS_VERDICT.get(j)
                if v == "blunder":
                    blunders += 1
                    caught += m["ep_label"] in SERIOUS
                if m["ep_label"] == "blunder":
                    ours_b += 1
                    ours_b_conf += v is not None
                if v is None:
                    clean += 1
                    clean_flag += m["ep_label"] in SERIOUS
                our_err += m["ep_label"] in ERRORS
                li_err += v is not None
            eo = eval_only_accuracy(r)
            s = r["summary"]
            for side in ("white", "black"):
                ref = g["accuracy"][side]
                if ref is not None:
                    acc_d.append(s[side]["accuracy"] - ref)
                    if eo[side] is not None:
                        acc_eo_d.append(eo[side] - ref)
                est = s[side]["estimated_rating"]
                if est:
                    pl_err.append(est["plays_like"] - g[f"{side}_elo"])
            res_ours.append((s["white"]["accuracy"], s["black"]["accuracy"], g["winner"]))
            res_li.append((g["accuracy"]["white"] or 0, g["accuracy"]["black"] or 0, g["winner"]))
            res_eo.append((eo["white"] or 0, eo["black"] or 0, g["winner"]))
            if s["white"]["estimated_rating"] and s["black"]["estimated_rating"]:
                res_pl.append((s["white"]["estimated_rating"]["plays_like"], s["black"]["estimated_rating"]["plays_like"], g["winner"]))
        players = 2 * len(games)
        out["lichess"][tc] = {
            "games": len(games),
            "li_blunder_caught": pct(caught, blunders),
            "li_blunders": blunders,
            "li_our_blunders_confirmed": pct(ours_b_conf, ours_b),
            "li_clean_false_alarm": pct(clean_flag, clean),
            "li_error_count_ratio": round(our_err / li_err, 2) if li_err else None,
            "errors_per_player_ours": round(our_err / players, 2) if players else None,
            "errors_per_player_lichess": round(li_err / players, 2) if players else None,
            "li_accuracy_mae": round(statistics.mean(map(abs, acc_d)), 2) if acc_d else None,
            "li_accuracy_bias": round(statistics.mean(acc_d), 2) if acc_d else None,
            "eval_only_accuracy_mae": round(statistics.mean(map(abs, acc_eo_d)), 2) if acc_eo_d else None,
            "winner_auc_our_accuracy": result_auc(res_ours),
            "winner_auc_lichess_accuracy": result_auc(res_li),
            "winner_auc_eval_only_accuracy": result_auc(res_eo),
            "winner_auc_played_like": result_auc(res_pl),
            "played_like_minus_rating_mean": round(statistics.mean(pl_err), 0) if pl_err else None,
        }

    # Chess.com: accuracy per player vs Chess.com's own.
    for tc in CLASSES + ("all",) if sets["chesscom"] else ():
        games = [g for g in sets["chesscom"] if tc in ("all", g["time_class"])]
        acc_d, acc_eo_d, res_ours, res_cc, res_eo, res_pl = [], [], [], [], [], []
        for g in games:
            r = review(read_game(g["pgn"]))
            eo = eval_only_accuracy(r)
            s = r["summary"]
            for side in ("white", "black"):
                acc_d.append(s[side]["accuracy"] - g["accuracy"][side])
                if eo[side] is not None:
                    acc_eo_d.append(eo[side] - g["accuracy"][side])
            res_ours.append((s["white"]["accuracy"], s["black"]["accuracy"], g["winner"]))
            res_cc.append((g["accuracy"]["white"], g["accuracy"]["black"], g["winner"]))
            res_eo.append((eo["white"] or 0, eo["black"] or 0, g["winner"]))
            if s["white"]["estimated_rating"] and s["black"]["estimated_rating"]:
                res_pl.append((s["white"]["estimated_rating"]["plays_like"], s["black"]["estimated_rating"]["plays_like"], g["winner"]))
        out["chesscom"][tc] = {
            "games": len(games),
            "cc_accuracy_mae": round(statistics.mean(map(abs, acc_d)), 2) if acc_d else None,
            "cc_accuracy_bias": round(statistics.mean(acc_d), 2) if acc_d else None,
            "eval_only_accuracy_mae": round(statistics.mean(map(abs, acc_eo_d)), 2) if acc_eo_d else None,
            "winner_auc_our_accuracy": result_auc(res_ours),
            "winner_auc_chesscom_accuracy": result_auc(res_cc),
            "winner_auc_eval_only_accuracy": result_auc(res_eo),
            "winner_auc_played_like": result_auc(res_pl),
        }

    # Puzzles.
    sol = sol_good = alive = alive_flag = 0
    for p in sets["puzzles"]:
        moves = review(puzzle_game(p), book_path=None)["moves"]
        if moves[0]["ep_best"] >= 0.15:
            alive += 1
            alive_flag += moves[0]["ep_label"] in ERRORS
        for m in moves[1::2]:
            sol += 1
            sol_good += m["ep_label"] in GOOD
    out["puzzles"] = {"puzzles": len(sets["puzzles"]), "puzzle_solution_good": pct(sol_good, sol), "puzzle_setup_flagged": pct(alive_flag, alive)}

    # Known cases: a move and the labels that count as right.
    passed, fails = 0, []
    for c in sets["cases"]:
        r = review(read_game(c["pgn"]), book_path=None)
        m = r["moves"][c["ply"] - 1]
        ok = m["ep_label"] in c["allowed"]
        passed += ok
        if not ok:
            fails.append({"case": c["name"], "ply": c["ply"], "san": m["san"], "got": m["ep_label"], "allowed": c["allowed"], "loss": round(m["ep_loss"], 3)})
    out["cases"] = {"cases": len(sets["cases"]), "cases_pass": pct(passed, len(sets["cases"])), "failures": fails}
    return out


def check(value: Any, op: str, target: Any) -> bool | None:
    if value is None:
        return None
    if op == ">=":
        return value >= target
    if op == "<=":
        return value <= target
    return target[0] <= value <= target[1]


def metric_cells(res: dict, key: str) -> list[tuple[str, Any]]:
    """(scope, value) for a metric: per time class for game sets, one value otherwise."""
    for section in ("lichess", "chesscom"):
        if key in res[section].get("all", {}):
            return [(tc, res[section][tc][key]) for tc in CLASSES + ("all",)]
    for section in ("puzzles", "cases"):
        if key in res[section]:
            return [("all", res[section][key])]
    return []


def fmt_target(op: str, t: Any) -> str:
    return f"{t[0]}–{t[1]}" if op == "between" else f"{op} {t}"


def write_doc(results: dict[str, dict], sets: dict[str, list]) -> None:
    names = list(results)
    lines = [
        "# Benchmark",
        "",
        "Generated by `python -m ep_model.benchmark.run score`. Fixed sets (`ep_model/benchmark/data`): "
        f"{len(sets['lichess'])} recent Lichess games with Lichess's own verdicts and accuracy, "
        f"{len(sets['chesscom'])} Chess.com games with Chess.com's own accuracy, {len(sets['puzzles'])} Lichess puzzles, "
        f"{len(sets['cases'])} known cases. Engine: Stockfish depth 17, 2 lines. Models: "
        + ", ".join(f"`{n}`" for n in names)
        + ".",
        "",
        "## Targets",
        "",
        "| Metric | Target | Scope | " + " | ".join(names) + " |",
        "|---|---|---|" + "---|" * len(names),
    ]
    for key, desc, op, target in TARGETS:
        scopes = [s for s, _ in metric_cells(results[names[0]], key)]
        for scope in scopes:
            cells = []
            for n in names:
                v = dict(metric_cells(results[n], key)).get(scope)
                ok = check(v, op, target)
                cells.append("–" if v is None else f"{v} {'✅' if ok else '❌'}")
            lines.append(f"| {desc} | {fmt_target(op, target)} | {scope} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## Realism: does the number pick the winner?",
        "",
        "Share of decisive games where the player with the higher value won (0.5 = coin flip). Reference accuracies shown for comparison.",
        "",
        "| Set | Scope | Value | " + " | ".join(names) + " |",
        "|---|---|---|" + "---|" * len(names),
    ]
    rows = [
        ("lichess", "winner_auc_our_accuracy", "our accuracy"),
        ("lichess", "winner_auc_eval_only_accuracy", "eval-only accuracy"),
        ("lichess", "winner_auc_lichess_accuracy", "Lichess's accuracy"),
        ("lichess", "winner_auc_played_like", "played-like rating"),
        ("chesscom", "winner_auc_our_accuracy", "our accuracy"),
        ("chesscom", "winner_auc_eval_only_accuracy", "eval-only accuracy"),
        ("chesscom", "winner_auc_chesscom_accuracy", "Chess.com's accuracy"),
        ("chesscom", "winner_auc_played_like", "played-like rating"),
    ]
    for section, key, label in rows:
        for tc in CLASSES + ("all",):
            vals = [results[n][section].get(tc, {}).get(key) for n in names]
            lines.append(f"| {section} | {tc} | {label} | " + " | ".join("–" if v is None else str(v) for v in vals) + " |")
    lines += ["", "## Details", ""]
    for n in names:
        r = results[n]
        if not r["lichess"]:
            continue
        lines.append(f"**{n}**: errors per player ours / Lichess: " + ", ".join(
            f"{tc} {r['lichess'][tc]['errors_per_player_ours']} / {r['lichess'][tc]['errors_per_player_lichess']}" for tc in CLASSES
        ) + "; accuracy bias vs Lichess " + ", ".join(f"{tc} {r['lichess'][tc]['li_accuracy_bias']:+}" for tc in CLASSES if r["lichess"][tc]["li_accuracy_bias"] is not None)
          + "; vs Chess.com " + ", ".join(f"{tc} {r['chesscom'][tc]['cc_accuracy_bias']:+}" for tc in CLASSES if r["chesscom"].get(tc, {}).get("cc_accuracy_bias") is not None) + ".")
        lines.append("")
    for n in names:
        r = results[n]
        for f in r["cases"]["failures"]:
            lines.append(f"- {n} case failed: {f['case']} ply {f['ply']} {f['san']}: got {f['got']} (loss {f['loss']}), expected {'/'.join(f['allowed'])}")
        if r["cases"]["failures"]:
            lines.append("")
    DOC.write_text("\n".join(lines) + "\n", encoding="utf-8")


def score(models: list[str], depth: int) -> None:
    sets = load_sets()
    evals = CachedEvals(depth)
    # A set not fully analysed yet (precompute still running) is left out rather than failing the run.
    for name in ("lichess", "chesscom"):
        fens = {f for g in sets[name] for f in game_fens(read_game(g["pgn"]))}
        if fens - evals.data.keys():
            LOG.warning("%s: %d of %d positions not analysed yet; skipping this set", name, len(fens - evals.data.keys()), len(fens))
            sets[name] = []
    RESULTS.mkdir(parents=True, exist_ok=True)
    results = {}
    for spec in models:
        name, _, path = spec.partition("=")
        t0 = time.time()
        results[name] = score_model(EPModel(Path(path)), sets, evals, depth)
        (RESULTS / f"{name}.json").write_text(json.dumps(results[name], indent=2), encoding="utf-8")
        LOG.info("%s scored in %.0fs", name, time.time() - t0)
    write_doc(results, sets)
    print(DOC.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    pre = sub.add_parser("precompute")
    pre.add_argument("--workers", type=int, default=10)
    sc = sub.add_parser("score")
    sc.add_argument("--model", action="append", required=True, help="name=model_dir (repeatable)")
    for s in (pre, sc):
        s.add_argument("--depth", type=int, default=17)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.cmd == "precompute":
        precompute(args.depth, args.workers)
    else:
        score(args.model, args.depth)
    return 0


if __name__ == "__main__":
    sys.exit(main())
