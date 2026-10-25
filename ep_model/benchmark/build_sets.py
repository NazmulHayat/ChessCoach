"""
Freeze the benchmark sets, so every model is scored on exactly the same games (files in ep_model/benchmark/data).

  lichess   Recent Lichess games the Lichess servers analysed (deeper engine): per-move verdicts and each
            player's accuracy, as Lichess shows them. From the public API, so not in our training month.
  chesscom  Chess.com games with Chess.com's own accuracy (public API, only for games someone reviewed),
            balanced over time classes and rating bins.
  puzzles   Lichess puzzles: a real blunder, then the one winning answer.
  cases     Known moves with a fixed right answer: games users reported, and textbook traps played at several
            ratings and clock situations (labels must not depend on who has more time).

Usage (repo root):
  python -m ep_model.benchmark.build_sets all
  python -m ep_model.benchmark.build_sets chesscom --per-class 100
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import chess
import httpx

from ep_model.phase_a.generate_rows import stream_games

LOG = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parents[2]
DATA = Path(__file__).resolve().parent / "data"
DUMP = REPO / "ep_model" / "raw" / "lichess_db_standard_rated_2026-02.pgn.zst"
PUZZLES_HEAD = REPO / "ep_model" / "raw" / "puzzles_head.csv"
UA = {"User-Agent": "ChessCoach/0.1 benchmark (github.com/NazmulHayat/ChessCoach)"}

CLASSES = ("bullet", "blitz", "rapid")
RATING_BINS = [(0, 800), (800, 1200), (1200, 1600), (1600, 2000), (2000, 4000)]


def rating_bin(r: int) -> int:
    return next(i for i, (lo, hi) in enumerate(RATING_BINS) if lo <= r < hi)


# ---------- Lichess ----------


def lichess_users(n: int, seed: int) -> list[str]:
    """Usernames of active players from the monthly dump (only used as a list of people to look up)."""
    rng = random.Random(seed)
    users: list[str] = []
    for game in stream_games(DUMP):
        for side in ("White", "Black"):
            name = game.headers.get(side)
            if name and name not in users and rng.random() < 0.3:
                users.append(name)
        if len(users) >= n:
            break
    rng.shuffle(users)
    return users


def build_lichess(per_class: int, seed: int) -> None:
    out: dict[str, list[dict]] = {c: [] for c in CLASSES}
    with httpx.Client(headers={**UA, "Accept": "application/x-ndjson"}, timeout=30) as client:
        for user in lichess_users(4000, seed):
            if all(len(out[c]) >= per_class for c in CLASSES):
                break
            need = [c for c in CLASSES if len(out[c]) < per_class]
            r = client.get(
                f"https://lichess.org/api/games/user/{user}",
                params={
                    "max": 15, "analysed": "true", "evals": "true", "clocks": "true", "accuracy": "true",
                    "pgnInJson": "true", "perfType": ",".join(need), "rated": "true",
                },
            )
            time.sleep(1.0)
            if r.status_code == 429:
                LOG.info("Lichess rate limit; waiting 60 s")
                time.sleep(60)
                continue
            if r.status_code != 200:
                continue
            taken = 0
            for line in r.text.splitlines():
                g = json.loads(line)
                speed = g.get("speed")
                if speed not in need or len(out[speed]) >= per_class or taken >= 2:
                    continue
                if g.get("variant") != "standard" or g.get("initialFen") or len(g.get("moves", "").split()) < 20:
                    continue
                players = g["players"]
                if any("analysis" not in players[s] or "rating" not in players[s] for s in ("white", "black")):
                    continue
                if any(players[s].get("provisional") for s in ("white", "black")):
                    continue
                out[speed].append(
                    {
                        "id": g["id"],
                        "time_class": speed,
                        "pgn": g["pgn"],
                        "white_elo": players["white"]["rating"],
                        "black_elo": players["black"]["rating"],
                        "winner": g.get("winner"),
                        "accuracy": {s: players[s]["analysis"].get("accuracy") for s in ("white", "black")},
                        # Lichess's verdict per ply ("" when none), from its own deeper analysis.
                        "judgments": [(a.get("judgment") or {}).get("name", "") for a in g.get("analysis", [])],
                    }
                )
                taken += 1
            LOG.info("lichess %s", {c: len(v) for c, v in out.items()})
    rows = [g for c in CLASSES for g in out[c]]
    write_jsonl(DATA / "lichess_games.jsonl", rows)


# ---------- Chess.com ----------


def build_chesscom(per_class: int, seed: int, max_requests: int = 3000) -> None:
    """
    Walk from player to opponent, steering toward the (time class, rating bin) cells still short of games.
    At most 2 games per player, only games that carry Chess.com's accuracy for both sides.
    """
    rng = random.Random(seed)
    per_cell = per_class // len(RATING_BINS)
    cells: dict[tuple[str, int], list[dict]] = defaultdict(list)
    seen_games: set[str] = set()
    visited: set[str] = set()
    candidates: dict[int, list[str]] = defaultdict(list)  # rating bin -> usernames seen there
    for u in ("hikaru", "danielnaroditsky", "chessbrah", "gothamchess", "annacramling"):
        candidates[4].append(u)
    requests = 0

    def short() -> list[int]:
        return [b for b in range(len(RATING_BINS)) if any(len(cells[(c, b)]) < per_cell for c in CLASSES)]

    with httpx.Client(headers=UA, timeout=30) as client:
        while short() and requests < max_requests:
            bins = [b for b in short() if candidates[b]] or [b for b in candidates if candidates[b]]
            if not bins:
                break
            b = rng.choice(bins)
            user = candidates[b].pop(rng.randrange(len(candidates[b])))
            if user in visited:
                continue
            visited.add(user)
            try:
                arch = client.get(f"https://api.chess.com/pub/player/{user}/games/archives").json().get("archives", [])
                requests += 1
                if not arch:
                    continue
                games = client.get(arch[-1]).json().get("games", [])
                requests += 1
            except (httpx.HTTPError, ValueError):
                continue
            taken = 0
            for g in reversed(games):
                for side in ("white", "black"):
                    opp = g[side]["username"]
                    if opp.lower() != user.lower() and opp not in visited:
                        candidates[rating_bin(g[side]["rating"])].append(opp)
                tc = g.get("time_class")
                if taken >= 2 or tc not in CLASSES or g.get("rules") != "chess" or not g.get("rated"):
                    continue
                if "accuracies" not in g or g["url"] in seen_games or "[SetUp" in g.get("pgn", ""):
                    continue
                me = "white" if g["white"]["username"].lower() == user.lower() else "black"
                cell = (tc, rating_bin(g[me]["rating"]))
                if len(cells[cell]) >= per_cell or g["pgn"].count(".") < 20:
                    continue
                seen_games.add(g["url"])
                winner = "white" if g["white"]["result"] == "win" else "black" if g["black"]["result"] == "win" else None
                cells[cell].append(
                    {
                        "id": g["url"].rsplit("/", 1)[-1],
                        "url": g["url"],
                        "time_class": tc,
                        "pgn": g["pgn"],
                        "white_elo": g["white"]["rating"],
                        "black_elo": g["black"]["rating"],
                        "winner": winner,
                        "accuracy": g["accuracies"],
                        "rating_bin": cell[1],
                    }
                )
                taken += 1
            if requests % 50 < 2:
                LOG.info("chesscom requests=%d %s", requests, {f"{c}/{b}": len(v) for (c, b), v in sorted(cells.items())})
    rows = [g for c in CLASSES for b in range(len(RATING_BINS)) for g in cells[(c, b)]]
    LOG.info("chesscom: %d games %s", len(rows), Counter(r["time_class"] for r in rows))
    write_jsonl(DATA / "chesscom_games.jsonl", rows)


# ---------- known cases ----------

# (name, moves, {ply: allowed labels}). Ply counts from 1 = White's first move.
TRAPS = [
    ("hangs queen", "e4 e5 Qh5 Nc6 Qxe5+ Nxe5", {5: ["blunder"], 6: ["best", "excellent"]}),
    ("allows mate in 1", "e4 e5 Bc4 Nc6 Qh5 Nf6 Qxf7#", {6: ["blunder", "miss"], 7: ["best", "great", "brilliant"]}),
    ("hangs bishop", "d4 e5 dxe5 d6 exd6 Bxd6 Bg5 Qxg5", {7: ["mistake", "blunder"], 8: ["best", "excellent"]}),
    ("misses free queen", "e4 e5 Qh5 Nc6 Qxe5+ Be7", {6: ["blunder", "miss"]}),
]
# Games users reported, with the reference verdict for a move (Lichess's server analysis).
REPORTED = [
    ("lichess nMuWq0F1 (bullet): queen for rook", "nMuWq0F1", {36: ["blunder"]}),
]


def _pgn(moves: str, elo: int, tc: str, clocks: tuple[int, int] | None) -> str:
    board = chess.Board()
    out = []
    for i, san in enumerate(moves.split()):
        num = f"{i // 2 + 1}. " if i % 2 == 0 else ""
        clk = ""
        if clocks:
            sec = clocks[i % 2]
            clk = f" {{ [%clk 0:{sec // 60:02d}:{sec % 60:02d}] }}"
        out.append(f"{num}{san}{clk}")
        board.push_san(san)
    head = f'[White "w"]\n[Black "b"]\n[WhiteElo "{elo}"]\n[BlackElo "{elo}"]\n[TimeControl "{tc}"]\n[Site "https://lichess.org/case"]\n\n'
    return head + " ".join(out) + " *\n"


def build_cases() -> None:
    cases = []
    for name, moves, expect in TRAPS:
        for elo in (800, 1500, 2200):
            # Rapid with no clocks; bullet where the mover's side is nearly flagging; bullet where the other side is.
            for tc, clocks, tag in (("600+0", None, "rapid"), ("60+0", (5, 50), "bullet, white 5s"), ("60+0", (50, 5), "bullet, black 5s")):
                pgn = _pgn(moves, elo, tc, clocks)
                for ply, allowed in expect.items():
                    cases.append({"name": f"{name} @{elo} {tag}", "pgn": pgn, "ply": ply, "allowed": allowed})
    with httpx.Client(headers=UA, timeout=30) as client:
        for name, gid, expect in REPORTED:
            pgn = client.get(f"https://lichess.org/game/export/{gid}", params={"clocks": "true", "evals": "false"}).text
            for ply, allowed in expect.items():
                cases.append({"name": name, "pgn": pgn, "ply": ply, "allowed": allowed})
    (DATA / "cases.json").write_text(json.dumps(cases, indent=1), encoding="utf-8")
    LOG.info("Wrote %d cases", len(cases))


# ---------- puzzles ----------


def build_puzzles(n: int, seed: int) -> None:
    with open(PUZZLES_HEAD, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    random.Random(seed).shuffle(rows)
    keep = ["PuzzleId", "FEN", "Moves", "Rating", "Themes"]
    with open(DATA / "puzzles.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keep)
        w.writeheader()
        for r in rows[:n]:
            w.writerow({k: r[k] for k in keep})


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    LOG.info("Wrote %d rows to %s", len(rows), path)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("which", choices=["lichess", "chesscom", "puzzles", "cases", "all"])
    p.add_argument("--per-class", type=int, default=None, help="Games per time class (lichess 50, chesscom 100)")
    p.add_argument("--puzzles", type=int, default=300)
    p.add_argument("--seed", type=int, default=2026)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.which in ("puzzles", "all"):
        build_puzzles(args.puzzles, args.seed)
    if args.which in ("cases", "all"):
        build_cases()
    if args.which in ("lichess", "all"):
        build_lichess(args.per_class or 50, args.seed)
    if args.which in ("chesscom", "all"):
        build_chesscom(args.per_class or 100, args.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
