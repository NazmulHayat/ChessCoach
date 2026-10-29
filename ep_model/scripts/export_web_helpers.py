"""
Parity fixtures for the TypeScript port of the review helpers (web/src/review/*.ts): inputs and the Python
reference outputs of special.py, tactics.py, the Polyglot book, rowgen helpers, ratings.py, accuracy.py and
rating_estimate.py. Positions come from the frozen benchmark sets.

Usage (repo root):
  python -m ep_model.scripts.export_web_helpers
"""

from __future__ import annotations

import csv
import io
import json
import math
import random
import sys
from pathlib import Path

import chess
import chess.pgn
import chess.polyglot

from ep_model.sampling import rowgen
from ep_model.review import accuracy, rating_estimate, ratings, special, tactics

REPO = Path(__file__).resolve().parents[2]
BENCH = REPO / "ep_model" / "benchmark" / "data"
BOOK = REPO / "ep_model" / "review" / "data" / "book.bin"
OUT = REPO / "web" / "src" / "review" / "__fixtures__"


def write(name: str, data) -> None:
    path = OUT / f"helpers_{name}.json"
    path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    print(f"{path.relative_to(REPO)}: {path.stat().st_size / 1e3:.0f} kB")


def benchmark_games() -> list[chess.pgn.Game]:
    with open(BENCH / "lichess_games.jsonl", encoding="utf-8") as f:
        return [chess.pgn.read_game(io.StringIO(json.loads(line)["pgn"])) for line in f if line.strip()]


def positions(rng: random.Random, n_puzzles: int, n_game: int) -> list[str]:
    fens: list[str] = []
    with open(BENCH / "puzzles.csv", encoding="utf-8") as f:
        for row in list(csv.DictReader(f))[:n_puzzles]:
            b = chess.Board(row["FEN"])
            fens.append(b.fen())
            moves = row["Moves"].split()
            b.push_uci(moves[0])  # the puzzle position itself (after the blunder)
            fens.append(b.fen())
    game_fens = []
    for g in benchmark_games():
        b = g.board()
        for mv in g.mainline_moves():
            b.push(mv)
            game_fens.append(b.fen())
    fens += rng.sample(game_fens, n_game)
    return fens


def square_name(sq):
    return None if sq is None else chess.square_name(sq)


def special_cases(rng: random.Random) -> dict:
    cases = []
    for fen in positions(rng, 120, 120):
        board = chess.Board(fen)
        if board.is_game_over():
            continue
        legal = list(board.legal_moves)
        see = {chess.square_name(sq): special.see(board, sq) for sq in chess.SQUARES if board.piece_at(sq)}
        gain, where = special.best_capture_gain(board)
        moves = []
        # sacrifice_points loops over all legal moves, so it is checked on a sample (captures and checks first).
        priority = [m for m in legal if board.is_capture(m) or board.gives_check(m)]
        sac_sample = set(priority[:4] + rng.sample(legal, min(3, len(legal))))
        for m in legal:
            hang = tactics.hanging_after(board, m)
            won = tactics.material_won(board, m)
            moves.append(
                {
                    "uci": m.uci(),
                    "capture_value": special._capture_value(board, m),
                    "material_given": special.material_given(board, m),
                    "sacrificed_piece": special.sacrificed_piece(board, m),
                    "takes_hanging": special.takes_hanging_material(board, m),
                    "sacrifice_points": special.sacrifice_points(board, m) if m in sac_sample else None,
                    "hanging_after": list(hang) if hang else None,
                    "material_won": list(won) if won else None,
                }
            )
        cases.append({"fen": fen, "see": see, "best_capture_gain": [gain, square_name(where)], "moves": moves})
    return {"positions": cases}


def tactic_cases(rng: random.Random) -> list[dict]:
    out = []
    for fen in positions(rng, 150, 150):
        board = chess.Board(fen)
        legal = [m.uci() for m in board.legal_moves]
        if not legal:
            continue
        for _ in range(4):
            played = rng.choice(legal)
            best = rng.choice(legal + [played, None])
            mate_before = rng.choice([None, None, None, 1, 2, 5, -3])
            mate_after = rng.choice([None, None, None, 1, 3, -2, 0])
            out.append(
                {
                    "fen": fen, "played": played, "best": best, "mate_before": mate_before, "mate_after": mate_after,
                    "hint": tactics.tactic_hint(fen, played, best, mate_before, mate_after),
                }
            )
    return out


def book_cases(rng: random.Random) -> list[dict]:
    out = []
    seen = set()
    with chess.polyglot.open_reader(str(BOOK)) as book:
        for g in benchmark_games():
            b = g.board()
            for k, mv in enumerate(g.mainline_moves()):
                if k >= 15:
                    break
                fen = b.fen(en_passant="fen")
                if fen not in seen:
                    seen.add(fen)
                    out.append(
                        {
                            "fen": fen,
                            "key": f"{chess.polyglot.zobrist_hash(b):016x}",
                            "moves": [e.move.uci() for e in book.find_all(b)],
                        }
                    )
                b.push(mv)
        # En passant / castling edge cases.
        for moves in ("e4 d5 e5 f5", "e4 a6 e5 d5", "e4 e5 Nf3 Nc6 Bc4 Bc5 O-O", "a4 b5 axb5 h6 Ra2", "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6"):
            b = chess.Board()
            for san in moves.split():
                b.push_san(san)
                fen = b.fen(en_passant="fen")
                out.append({"fen": fen, "key": f"{chess.polyglot.zobrist_hash(b):016x}", "moves": [e.move.uci() for e in book.find_all(b)]})
    return out


def rowgen_cases() -> dict:
    tcs = ["300+0", "180+2", "60", "-", "?", "", None, " 600 + 5 ", "abc", "15+", "1800+30", "0+1", "+5"]
    clocks = ["[%clk 0:05:00]", "{ [%clk 1:02:03.5] }", "[%clk 4:59]", "[%clk  0:00:07 ]", "no clock", None, "[%clk x:y]", "[%eval 0.3] [%clk 0:00:59.9]"]
    headers = ["0:05:00", "5:00", "", None, "1:00:00", "bad"]
    return {
        "time_control": [[tc, list(rowgen.parse_time_control(tc))] for tc in tcs],
        "time_class": [[x, rowgen.classify_time_class(x)] for x in [None, 0, 59, 179, 180, 479, 480, 1499, 1500, 10800]],
        "rating_band": [[x, rowgen.rating_band_from_average(x)] for x in [0, 500.7, 999.9, 1000, 1199, 1200, 1650.5, 1999.99, 2000, 2999, 3000, 3500, -5]],
        "phase": [[x, rowgen.game_phase_from_half_moves(x)] for x in [0, 19, 20, 59, 60, 200]],
        "clock_comment": [[c, rowgen.parse_clock_comment(c)] for c in clocks],
        "clock_header": [[h, rowgen.parse_clock_header(h)] for h in headers],
    }


def ratings_cases() -> dict:
    out = {"to": [], "from": [], "pool": []}
    for pool in ("lichess", "chesscom"):
        for tc in ("bullet", "blitz", "rapid", "classical", "unknown"):
            for elo in (100, 400, 801, 1000, 1234, 1500, 1785, 2000, 2350, 3000):
                out["to"].append([elo, pool, tc, ratings.to_lichess_scale(elo, pool, tc)])
                out["from"].append([elo, pool, tc, ratings.from_lichess_scale(elo, pool, tc)])
    for h in [{"Site": "https://www.chess.com/game/live/1"}, {"Site": "https://lichess.org/abc"}, {"Link": "https://www.Chess.com/x"}, {}]:
        out["pool"].append([h, ratings.detect_pool(h)])
    return out


def accuracy_cases(rng: random.Random) -> dict:
    games = []
    for g in benchmark_games()[:60]:
        cps = [15.0]
        for node in g.mainline():
            ev = node.eval()
            if ev is None:
                break
            cps.append(float(ev.white().score(mate_score=100_000)))
        if len(cps) > 10:
            cps = [max(-1000.0, min(1000.0, c)) if abs(c) < 50_000 else c for c in cps]
            games.append({"cps": cps, "white_starts": True, "result": accuracy.lichess_game_accuracy(cps, True)})
    for _ in range(20):
        n = rng.randint(2, 80)
        cps = [rng.uniform(-1500, 1500) for _ in range(n)]
        ws = rng.random() < 0.5
        games.append({"cps": cps, "white_starts": ws, "result": accuracy.lichess_game_accuracy(cps, ws)})
    vol = []
    for n in (2, 3, 5, 11, 25, 40, 81, 160):
        w = [rng.uniform(0, 100) for _ in range(n)]
        vol.append({"win": w, "weights": accuracy.volatility_weights(w)})
    comb = []
    for n in (0, 1, 2, 7, 30):
        a = [rng.choice([0.0, 0.5, rng.uniform(0, 100), 100.0]) for _ in range(n)]
        w = [rng.uniform(0.5, 12) for _ in range(n)]
        comb.append({"accs": a, "weights": w, "result": accuracy.combine(a, w)})
    ep = []
    for n in (3, 30, 90):
        e = [rng.random() for _ in range(n)]
        ep.append({"ep": e, "weights": accuracy.ep_move_weights(e)})
    return {
        "win_percent": [[c, accuracy.win_percent(c)] for c in [-5000, -1000, -350.5, -1, 0, 15, 99.9, 1000, 2500]],
        "move_accuracy": [[d, b, accuracy.move_accuracy_pct(d, b)] for d in [-3, 0, 0.001, 1, 5.5, 20, 49.9, 80, 100] for b in (0.0, 1.0)],
        "games": games,
        "volatility": vol,
        "combine": comb,
        "ep_weights": ep,
    }


def rating_cases(rng: random.Random) -> dict:
    ests = []
    for _ in range(80):
        acc = {"white": rng.choice([rng.uniform(40, 100), 100.0, 72.5]), "black": rng.choice([rng.uniform(40, 100), 64.0])}
        ratings = {"white": rng.randint(400, 2800), "black": rng.randint(400, 2800)}
        moves = {"white": rng.choice([5, 9, 10, 30]), "black": rng.choice([9, 10, 30])}
        tc = rng.choice(["bullet", "blitz", "rapid", "classical", "unknown"])
        ests.append({"accuracy": acc, "ratings": ratings, "moves": moves, "time_class": tc,
                     "result": rating_estimate.game_ratings(acc, ratings, moves, tc)})
    meta = rating_estimate.load_meta()
    plays = [[tc, a, rating_estimate.plays_like(a, tc, meta)] for tc in ["bullet", "blitz", "rapid", "classical", "unknown"] for a in [0.0, 55.5, 70.0, 80.25, 90.0, 100.0]]
    phases = []
    for fen, ply, in_book in [
        (chess.STARTING_FEN, 1, True), (chess.STARTING_FEN, 25, False), (chess.STARTING_FEN, 25, True),
        ("8/5k2/8/3K4/8/8/2R5/8 w - - 0 50", 99, False), ("r3k2r/8/8/8/8/8/8/R2QK2R w KQkq - 0 30", 59, False),
        ("rn2k2r/8/8/8/8/8/8/RN1QK2R w KQkq - 0 30", 40, False),
    ]:
        phases.append([fen, ply, in_book, rating_estimate.phase_of(chess.Board(fen), ply, in_book)])
    grades = []
    for _ in range(30):
        n = rng.randint(0, 12)
        moves = [
            {"accuracy": rng.choice([100.0, rng.uniform(30, 100)]), "weight": rng.uniform(0.5, 12), "ep_label": rng.choice(["book", "best", "good", "blunder"])}
            for _ in range(n)
        ]
        if rng.random() < 0.2:
            for m in moves:
                m["ep_label"] = "book"
        grades.append({"moves": moves, "result": rating_estimate.phase_grade(moves)})
    return {
        "win_prob": [[c, rating_estimate.win_prob(c)] for c in [-3000, -300, 0, 42, 1000, 5000]],
        "move_accuracy": [[x, rating_estimate.move_accuracy(x)] for x in [0, 0.001, 0.05, 0.2, 0.7, 1.5]],
        "estimates": ests,
        "plays_like": plays,
        "phase_of": phases,
        "phase_grade": grades,
    }


def label_rule_cases(rng: random.Random) -> dict:
    great, miss, brill, thr = [], [], [], []
    for _ in range(400):
        args = [rng.random() < 0.7, rng.random(), rng.choice([None, rng.random()]), rng.randint(600, 2800), rng.choice([1, 2, 30]), rng.random() < 0.2, rng.random() < 0.05]
        great.append([args, special.is_great(*args)])
        margs = [rng.random() < 0.2, rng.uniform(0, 0.4), rng.random(), rng.choice([None, rng.uniform(0, 0.5)]), rng.choice([None, rng.random()])]
        miss.append([margs, special.is_miss(*margs)])
        bargs = [rng.random() < 0.8, rng.random(), rng.choice([None, rng.random(), 0.95]), rng.choice([0, 1, 2, 3, 5, 9]), rng.random() < 0.6]
        brill.append([bargs, special.is_brilliant(*bargs)])
    for elo in (500, 1000, 1300, 1600, 2200, 2900):
        thr.append([elo, special.thresholds_for(elo).great_gap])
    # Main lines for sacrifice_holds: random legal lines from benchmark positions, captures preferred.
    holds = []
    for fen in positions(rng, 40, 160):
        b = chess.Board(fen)
        line = []
        for _ in range(rng.choice([2, 4, 6, 8])):
            legal = list(b.legal_moves)
            if not legal:
                break
            caps = [m for m in legal if b.is_capture(m)]
            mv = rng.choice(caps if caps and rng.random() < 0.7 else legal)
            line.append(mv.uci())
            b.push(mv)
        holds.append([fen, line, special.sacrifice_holds(chess.Board(fen), line)])
    return {"great": great, "miss": miss, "brilliant": brill, "holds": holds, "thresholds": thr, "bands": [[x, special.outcome_band(x)] for x in [0, 0.299, 0.3, 0.5, 0.7, 0.701, 1]]}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    write("special", special_cases(random.Random(1)))
    write("tactics", tactic_cases(random.Random(2)))
    write("book", book_cases(random.Random(3)))
    write("rowgen", rowgen_cases())
    write("ratings", ratings_cases())
    write("accuracy", accuracy_cases(random.Random(4)))
    write("rating", rating_cases(random.Random(5)))
    write("rules", label_rule_cases(random.Random(6)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
