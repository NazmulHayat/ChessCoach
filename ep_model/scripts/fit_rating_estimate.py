"""
Fit the "game rating" estimate: a player's rating from how accurately they played one game.

Data: games in the Lichess dump that Lichess's servers already analysed ([%eval] after every move), so
per-move accuracy is free and the true rating is known. Features are rating-free on purpose (the Lichess
win% curve, not the EP model, which takes the player's rating as input); see rating_estimate.features:
accuracy, blunder / mistake / inaccuracy / precise-move rates, number of moves, mean |eval|, accuracy in
balanced positions and their share, time class. The opponent's rating is deliberately not a feature.

Game rating = performance relative to your own rating, as Chess.com describes it: compare the quality of
your moves with what players at your rating typically produce, and move your rating up or down by that.
  1. LightGBM (L1) turns the features into a quality score s.
  2. "Plays like" X: the rating whose median score equals s (inverse of the median-score-by-rating curve).
  3. Game rating = R + k (X - R), R = your rating. One game is noisy evidence, so k is the share of the
     spread of X - R that real performance swings explain, using Elo's classic assumption that a player's
     single-game performance varies with an SD of 200 points: k = 200^2 / Var(X - R), per time class.
Two versions were tried and rejected: predicting the rating directly regresses every game to the average
(a 99.7-accuracy game by a ~2000 player came out ~1500), and showing X itself spreads far too wide (blitz
MAE 430 vs 362 for always guessing the median).
A first version, least squares on accuracy and error rates per time class, reached blitz MAE 341 vs 364
for the median baseline; the balanced-position features matter.
Reports MAE on held-out games (both players of a game in the same split) against predicting the time
class's median rating.

Usage (repo root):
  python -m ep_model.scripts.fit_rating_estimate --games 200000
  → ep_model/review/data/rating_lgbm.txt + rating_estimate.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import zstandard

from ep_model.harvest.lichess_evals import EVAL_RE, GAME_SEP, HEADER_RE, MOVE_RE, parse_eval
from ep_model.sampling.rowgen import classify_time_class, parse_result_header, parse_time_control
from ep_model.review.rating_estimate import FEATURE_NAMES, META_FILE, MIN_MOVES, MODEL_FILE, TIME_CLASSES, features, win_prob

LOG = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parents[2]
ELO_GAME_SD = 200.0  # Elo's per-game performance spread
PARAMS = {"objective": "l1", "learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 200, "verbose": -1}
ROUNDS = 400
BIN = 100  # rating bin width for the inverse mapping
MIN_BIN_N = 200


def _cp(ev: tuple[int | None, int | None]) -> float:
    cp, mate = ev
    if mate is not None:
        return 1000.0 if mate > 0 else -1000.0
    return float(cp)


def sides_from_game(text: str) -> list[dict]:
    """Per-player raw win% losses for one fully analysed game (moves after the first)."""
    split = text.find("\n\n")
    if split == -1 or "[%eval" not in text:
        return []
    h = dict(HEADER_RE.findall(text[:split]))
    try:
        elos = {"w": int(h["WhiteElo"]), "b": int(h["BlackElo"])}
    except (KeyError, ValueError):
        return []
    if h.get("Variant", "Standard") != "Standard":
        return []
    init, _ = parse_time_control(h.get("TimeControl"))
    if init is None:
        return []
    tc = classify_time_class(init)
    evals: dict[int, tuple[int | None, int | None]] = {}
    for m in MOVE_RE.finditer(text[split + 2 :]):
        ev = parse_eval(m.group(3))
        if ev is not None:
            evals[(int(m.group(1)) - 1) * 2 + (0 if m.group(2) == "." else 1)] = ev
    if not evals:
        return []
    n = max(evals) + 1
    losses: dict[str, list[float]] = {"w": [], "b": []}
    cps: dict[str, list[float]] = {"w": [], "b": []}
    for i in range(1, n):
        if (i - 1) not in evals or i not in evals:
            continue
        side = "w" if i % 2 == 0 else "b"
        sign = 1.0 if side == "w" else -1.0
        before = win_prob(sign * _cp(evals[i - 1]))
        after = win_prob(sign * _cp(evals[i]))
        losses[side].append(max(0.0, before - after))
        cps[side].append(abs(_cp(evals[i - 1])))
    out = []
    for side, ls in losses.items():
        if len(ls) >= MIN_MOVES:
            res_white, _ = parse_result_header(h.get("Result"))
            score = None if res_white is None else (res_white if side == "w" else 1.0 - res_white)
            out.append({"time_class": tc, "elo": elos[side], "score": score, "x": features(ls, cps[side], tc)})
    return out


def stream_sides(path: Path, max_games: int) -> list[dict]:
    rows: list[dict] = []
    games = 0
    with open(path, "rb") as f:
        reader = zstandard.ZstdDecompressor().stream_reader(f, read_size=4 * 1024 * 1024)
        carry = b""
        while games < max_games:
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
                sides = sides_from_game(raw.decode("utf-8", "replace"))
                if sides:
                    for sd in sides:
                        sd["game"] = games
                    rows.extend(sides)
                    games += 1
                    if games >= max_games:
                        break
            LOG.info("%d analysed games, %d player-games", games, len(rows))
    return rows


def inverse_table(score: np.ndarray, rating: np.ndarray) -> dict[str, list[float]]:
    """Median score per rating bin, made increasing, for score -> rating interpolation."""
    lo, hi = int(np.floor(rating.min() / BIN) * BIN), int(np.ceil(rating.max() / BIN) * BIN)
    centers, medians = [], []
    for b in range(lo, hi, BIN):
        sel = (rating >= b) & (rating < b + BIN)
        if sel.sum() >= MIN_BIN_N:
            centers.append(b + BIN / 2)
            medians.append(float(np.median(score[sel])))
    med = np.maximum.accumulate(np.array(medians))
    med = med + np.arange(len(med)) * 1e-6  # strictly increasing for np.interp
    return {"score": [round(float(v), 4) for v in med], "rating": centers}


def apply_inverse(score: np.ndarray, table: dict[str, list[float]]) -> np.ndarray:
    return np.interp(score, table["score"], table["rating"])


def fit(rows: list[dict], seed: int = 0) -> tuple[lgb.Booster, dict, dict]:
    X = np.array([r["x"] for r in rows])
    y = np.array([r["elo"] for r in rows], dtype=float)
    games = np.array([r["game"] for r in rows])
    test = np.random.RandomState(seed).rand(games.max() + 1)[games] < 0.2
    cat = [FEATURE_NAMES.index("time_class")]
    booster = lgb.train(PARAMS, lgb.Dataset(X[~test], y[~test], feature_name=FEATURE_NAMES, categorical_feature=cat), ROUNDS)
    score_tr, score_te = booster.predict(X[~test]), booster.predict(X[test])
    report: dict[str, dict] = {}
    tables: dict[str, dict] = {}
    for tc, code in TIME_CLASSES.items():
        tr, te = X[~test][:, cat[0]] == code, X[test][:, cat[0]] == code
        if te.sum() < 500:
            continue
        tables[tc] = inverse_table(score_tr[tr], y[~test][tr])
        x_tr = apply_inverse(score_tr[tr], tables[tc])
        k = float(np.clip(ELO_GAME_SD**2 / np.var(x_tr - y[~test][tr]), 0.05, 1.0))
        tables[tc]["k"] = round(k, 4)
        truth = y[test][te]
        x_te = apply_inverse(score_te[te], tables[tc])
        est = truth + k * (x_te - truth)
        # Validity: players whose game rating is above their rating should score better in that game.
        res = np.array([r["score"] if r["score"] is not None else np.nan for r, t in zip(rows, test) if t])[te]
        gap = est - truth
        by_gap = {}
        for name, lo, hi in (("below -50", -1e9, -50), ("-50 to +50", -50, 50), ("above +50", 50, 1e9)):
            sel = (gap >= lo) & (gap < hi) & ~np.isnan(res)
            if sel.sum() >= 100:
                by_gap[name] = {"n": int(sel.sum()), "mean_score": round(float(np.mean(res[sel])), 3)}
        base = np.median(y[~test][tr])
        # Does a typical player at rating R get an estimate near R? Median estimate per 200-point band.
        bands = {}
        for b in range(800, 2600, 200):
            sel = (truth >= b) & (truth < b + 200)
            if sel.sum() >= 100:
                bands[f"{b}-{b + 200}"] = {"n": int(sel.sum()), "median_estimate": int(np.median(est[sel]))}
        report[tc] = {
            "n_train": int(tr.sum()),
            "n_test": int(te.sum()),
            "k": round(k, 3),
            "mean_score_by_game_rating_gap": by_gap,
            "plays_like_mae": round(float(np.mean(np.abs(x_te - truth))), 1),
            "mae": round(float(np.mean(np.abs(est - truth))), 1),
            "mae_regression": round(float(np.mean(np.abs(score_te[te] - truth))), 1),
            "mae_median_baseline": round(float(np.mean(np.abs(base - truth))), 1),
            "corr": round(float(np.corrcoef(est, truth)[0, 1]), 3),
            "estimate_sd": round(float(np.std(est)), 1),
            "true_sd": round(float(np.std(truth)), 1),
            "regression_sd": round(float(np.std(score_te[te])), 1),
            "resid_sd": round(float(np.std(est - truth)), 1),
            "posterior_sd": round(ELO_GAME_SD * (1 - k) ** 0.5, 1),
            "median_estimate_by_true_rating": bands,
        }
        LOG.info("%s: k=%.3f, plays-like MAE %.0f, mean score by game-rating gap %s", tc, k, report[tc]["plays_like_mae"], by_gap)
    return booster, report, tables


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--dump", type=Path, default=REPO / "ep_model" / "raw" / "lichess_db_standard_rated_2026-02.pgn.zst")
    p.add_argument("--games", type=int, default=200_000, help="Analysed games to use")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    t0 = time.time()
    rows = stream_sides(args.dump, args.games)
    booster, report, tables = fit(rows)
    booster.save_model(str(MODEL_FILE))
    meta = {
        "features": FEATURE_NAMES,
        "inverse": tables,
        "posterior_sd": {tc: r["posterior_sd"] for tc, r in report.items()},
        "report": report,
        "games": args.games,
        "player_games": len(rows),
        "min_moves": MIN_MOVES,
        "seconds": round(time.time() - t0, 1),
        "source": "Lichess 2026-02 dump, games with server analysis; ratings on the Lichess scale",
    }
    META_FILE.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
