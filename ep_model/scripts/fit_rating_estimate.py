"""
Fit the "game rating" curves: which rating typically plays a game at a given accuracy.

Data: games in the Lichess dump that Lichess's servers already analysed ([%eval] after every move), so
both players' game accuracy (Lichess's formula, the same one the app shows) is free and their ratings
are known.

Game rating ("played like a 1700") must follow the accuracy the app shows: in one game, the player with
the higher accuracy never gets the lower game rating, and across games more accuracy never means less.
  1. Per time class, the median game accuracy of players in each 100-point rating bin, made increasing
     (pool-adjacent-violators). Inverting it gives X(accuracy): the rating whose typical game this was.
  2. Both players are anchored on the same number, the game's average rating, so their order is decided
     by accuracy alone: game rating = anchor + 400 tanh((X - anchor) / spread), within FIDE's single-game
     bound of ±400. spread = SD of X - rating in that time class, so the limit is approached smoothly
     (with a hard cap, or spread = 400, most bullet players landed on it and tied).
The app's accuracy runs on our engine's evals, a little above Lichess's (docs/benchmark.md, accuracy
bias); that offset is subtracted before the lookup.

A previous version turned several features (error rates, accuracy in balanced positions, mean |eval|) into
a LightGBM quality score. It ranked players slightly better but could contradict the accuracy on screen:
Morphy's Opera Game, 98.8 accuracy against 85.1, came out 1300 vs 1200 for two 1500s.

Reports, on held-out games: the share of games where the order of game ratings contradicts the order
of accuracies (must be 0), how often the higher game rating won, and mean score by game rating vs rating.

Usage (repo root):
  python -m ep_model.scripts.fit_rating_estimate --games 200000
  → ep_model/review/data/rating_estimate.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import zstandard

from ep_model.harvest.lichess_evals import GAME_SEP, HEADER_RE, MOVE_RE, parse_eval
from ep_model.review.accuracy import lichess_game_accuracy
from ep_model.review.rating_estimate import META_FILE, MIN_MOVES, game_ratings, plays_like
from ep_model.sampling.rowgen import classify_time_class, parse_result_header, parse_time_control

LOG = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parents[2]
BIN = 100  # rating bin width
MIN_BIN_N = 200
# Our accuracy minus Lichess's on the same games, per time class (docs/benchmark.md, "accuracy bias vs
# Lichess" for the shipped model). Classical has no benchmark games; rapid is the closest.
ACCURACY_OFFSET = {"bullet": 2.58, "blitz": 2.59, "rapid": 2.17, "classical": 2.17}


def _cp(ev: tuple[int | None, int | None]) -> float:
    cp, mate = ev
    if mate is not None:
        return 1000.0 if mate > 0 else -1000.0
    return float(cp)


def game_from_text(text: str) -> dict | None:
    """Both players' rating, Lichess game accuracy and result for one fully analysed game."""
    split = text.find("\n\n")
    if split == -1 or "[%eval" not in text:
        return None
    h = dict(HEADER_RE.findall(text[:split]))
    try:
        elos = {"white": int(h["WhiteElo"]), "black": int(h["BlackElo"])}
    except (KeyError, ValueError):
        return None
    if h.get("Variant", "Standard") != "Standard":
        return None
    init, _ = parse_time_control(h.get("TimeControl"))
    if init is None:
        return None
    evals = []
    for m in MOVE_RE.finditer(text[split + 2 :]):
        ev = parse_eval(m.group(3))
        if ev is None:
            break  # analysis stops at the end of the game; a gap means it isn't fully analysed
        evals.append(_cp(ev))
    if len(evals) < 2 * MIN_MOVES:
        return None
    acc = lichess_game_accuracy([15.0] + evals)
    res_white, _ = parse_result_header(h.get("Result"))
    return {
        "time_class": classify_time_class(init),
        "elo": elos,
        "accuracy": acc,
        "moves": {"white": (len(evals) + 1) // 2, "black": len(evals) // 2},
        "score_white": res_white,
    }


def stream_games(path: Path, max_games: int) -> list[dict]:
    games: list[dict] = []
    with open(path, "rb") as f:
        reader = zstandard.ZstdDecompressor().stream_reader(f, read_size=4 * 1024 * 1024)
        carry = b""
        while len(games) < max_games:
            data = reader.read(32 * 1024 * 1024)
            if not data:
                break
            buf = carry + data
            cut = buf.rfind(GAME_SEP)
            carry = buf[cut + 2 :] if cut > 0 else buf
            if cut <= 0:
                continue
            for raw in buf[:cut].split(GAME_SEP):
                if b"[%eval" not in raw:
                    continue
                g = game_from_text(raw.decode("utf-8", "replace"))
                if g is not None:
                    games.append(g)
                    if len(games) >= max_games:
                        break
            LOG.info("%d analysed games", len(games))
    return games


def _isotonic(y: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Pool-adjacent-violators: the closest non-decreasing sequence (weighted least squares)."""
    blocks: list[list[float]] = []  # [mean, weight, count]
    for v, wt in zip(y, w):
        blocks.append([float(v), float(wt), 1])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            m2, w2, c2 = blocks.pop()
            m1, w1, c1 = blocks.pop()
            blocks.append([(m1 * w1 + m2 * w2) / (w1 + w2), w1 + w2, c1 + c2])
    return np.concatenate([[m] * c for m, _, c in blocks])


def accuracy_curve(acc: np.ndarray, rating: np.ndarray) -> dict[str, list[float]]:
    """Median accuracy per rating bin, made increasing (strictly, for interpolation)."""
    lo, hi = int(np.floor(rating.min() / BIN) * BIN), int(np.ceil(rating.max() / BIN) * BIN)
    centers, medians, counts = [], [], []
    for b in range(lo, hi, BIN):
        sel = (rating >= b) & (rating < b + BIN)
        if sel.sum() >= MIN_BIN_N:
            centers.append(b + BIN / 2)
            medians.append(float(np.median(acc[sel])))
            counts.append(int(sel.sum()))
    med = _isotonic(np.array(medians), np.array(counts, dtype=float))
    med = med + np.arange(len(med)) * 1e-3
    return {"accuracy": [round(float(v), 3) for v in med], "rating": centers}


def evaluate(games: list[dict], meta: dict) -> dict[str, dict]:
    """Held-out checks per time class, with Lichess's own accuracy (so no offset)."""
    no_offset = {**meta, "offset": {tc: 0.0 for tc in meta["offset"]}}
    report: dict[str, dict] = {}
    for tc in meta["curves"]:
        sub = [g for g in games if g["time_class"] == tc]
        if len(sub) < 500:
            continue
        contradictions = ties = 0
        picks: list[float] = []
        gaps: list[tuple[float, float]] = []
        err: list[float] = []
        for g in sub:
            est = game_ratings(g["accuracy"], g["elo"], g["moves"], tc, no_offset)
            if est["white"] is None or est["black"] is None:
                continue
            w, b = est["white"]["plays_like"], est["black"]["plays_like"]
            aw, ab = g["accuracy"]["white"], g["accuracy"]["black"]
            if (aw - ab) * (w - b) < 0:
                contradictions += 1
            ties += round(w, -2) == round(b, -2)  # as shown, rounded to 100
            for side, s in (("white", g["score_white"]), ("black", None if g["score_white"] is None else 1 - g["score_white"])):
                err.append(est[side]["plays_like"] - g["elo"][side])
                if s is not None:
                    gaps.append((est[side]["plays_like"] - g["elo"][side], s))
            if g["score_white"] in (0.0, 1.0) and w != b:
                picks.append(float((w > b) == (g["score_white"] == 1.0)))
        by_gap = {}
        for name, lo, hi in (("below -50", -1e9, -50), ("-50 to +50", -50, 50), ("above +50", 50, 1e9)):
            sel = [s for d, s in gaps if lo <= d < hi]
            if len(sel) >= 100:
                by_gap[name] = {"n": len(sel), "mean_score": round(float(np.mean(sel)), 3)}
        n = len(sub)
        report[tc] = {
            "games": n,
            "order_contradicts_accuracy": contradictions,
            "same_shown_game_rating_pct": round(100 * ties / n, 1),
            "higher_game_rating_won_pct": round(100 * float(np.mean(picks)), 1) if picks else None,
            "mean_game_rating_minus_rating": round(float(np.mean(err)), 1),
            "mean_score_by_game_rating_gap": by_gap,
        }
        LOG.info("%s: %s", tc, report[tc])
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--dump", type=Path, default=REPO / "ep_model" / "raw" / "lichess_db_standard_rated_2026-02.pgn.zst")
    p.add_argument("--games", type=int, default=200_000, help="Analysed games to use")
    p.add_argument("--cache", type=Path, help="JSON file of parsed games: read if present, else written")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    t0 = time.time()
    if args.cache and args.cache.is_file():
        games = json.loads(args.cache.read_text(encoding="utf-8"))[: args.games]
    else:
        games = stream_games(args.dump, args.games)
        if args.cache:
            args.cache.write_text(json.dumps(games), encoding="utf-8")
    test = np.random.RandomState(0).rand(len(games)) < 0.2
    train = [g for g, t in zip(games, test) if not t]
    curves = {}
    for tc in ("bullet", "blitz", "rapid", "classical"):
        acc = np.array([g["accuracy"][s] for g in train if g["time_class"] == tc for s in ("white", "black")])
        rating = np.array([g["elo"][s] for g in train if g["time_class"] == tc for s in ("white", "black")], dtype=float)
        if len(acc) >= 20 * MIN_BIN_N:
            curves[tc] = accuracy_curve(acc, rating)
    meta = {"curves": curves, "offset": ACCURACY_OFFSET, "spread": {}}
    for tc, curve in curves.items():
        acc = np.array([g["accuracy"][s] for g in train if g["time_class"] == tc for s in ("white", "black")])
        rating = np.array([g["elo"][s] for g in train if g["time_class"] == tc for s in ("white", "black")], dtype=float)
        lichess_scale = {"curves": {tc: curve}, "offset": {tc: 0.0, "blitz": 0.0}}
        x = np.array([plays_like(a, tc, lichess_scale) for a in acc])
        meta["spread"][tc] = round(float(np.std(x - rating)), 1)
    LOG.info("spread of X - rating: %s", meta["spread"])
    report = evaluate([g for g, t in zip(games, test) if t], meta)
    meta.update({
        "report": report,
        "games": len(games),
        "seconds": round(time.time() - t0, 1),
        "source": "Lichess 2026-02 dump, games with server analysis; ratings on the Lichess scale",
    })
    META_FILE.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
