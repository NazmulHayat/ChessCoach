"""
Compare the trained EP model against eval-only baselines on held-out games.

Baselines:
  - constant:        mean training outcome (floor any model must beat)
  - lichess_formula: Lichess win% curve, 1 / (1 + exp(-0.00368208 * cp)), cp clipped to ±1000
  - eval_logistic:   logistic fit on clipped cp only, trained on the same train games
  - eval_lgbm:       LightGBM on cp_stm_proxy only (same model class, no rating / clock context)

--extra-model NAME=DIR adds other trained EP models (e.g. one trained on harvested Lichess evals)
to the same comparison on the same held-out games.

Usage (repo root, after phase_c.train):
  python -m ep_model.phase_c.evaluate -v
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from ep_model.phase_c.prepare import (
    build_training_frame,
    load_eval_parquet,
    metrics_regression,
)

LOG = logging.getLogger(__name__)

LICHESS_K = 0.00368208
CP_CLIP = 1000.0
# Centipawn window for the "same eval, different players" table.
SLICE_CP = (100.0, 200.0)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def lichess_expected(cp: np.ndarray) -> np.ndarray:
    return _sigmoid(LICHESS_K * np.clip(cp, -CP_CLIP, CP_CLIP))


def fit_logistic_1d(x: np.ndarray, y: np.ndarray, iters: int = 50) -> tuple[float, float]:
    """Newton's method for p = sigmoid(a + b*x) with soft labels in [0, 1]."""
    X = np.column_stack([np.ones_like(x), x])
    w = np.zeros(2)
    for _ in range(iters):
        p = _sigmoid(X @ w)
        grad = X.T @ (p - y)
        hess = (X * (p * (1 - p))[:, None]).T @ X + 1e-9 * np.eye(2)
        step = np.linalg.solve(hess, grad)
        w -= step
        if np.max(np.abs(step)) < 1e-10:
            break
    return float(w[0]), float(w[1])


def _metrics_by(y: np.ndarray, preds: dict[str, np.ndarray], groups: pd.Series, min_n: int = 200) -> dict:
    out: dict[str, dict] = {}
    for g in sorted(groups.astype(str).unique()):
        m = (groups.astype(str) == g).to_numpy()
        if m.sum() < min_n:
            continue
        out[g] = {"n": int(m.sum()), **{name: metrics_regression(y[m], p[m]) for name, p in preds.items()}}
    return out


def row_log_loss(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    q = np.clip(p, 1e-6, 1.0 - 1e-6)
    return -(y * np.log(q) + (1.0 - y) * np.log(1.0 - q))


def paired_bootstrap(y: np.ndarray, p_new: np.ndarray, p_ref: np.ndarray, games: pd.Series, n: int = 1000, seed: int = 0) -> dict:
    """Log-loss difference (new - ref) with a 95% CI from resampling whole games (rows in a game are correlated)."""
    diff = row_log_loss(y, p_new) - row_log_loss(y, p_ref)
    codes, _ = pd.factorize(games.astype(str))
    sums = np.bincount(codes, weights=diff)
    counts = np.bincount(codes).astype(np.float64)
    rng = np.random.RandomState(seed)
    boots = np.empty(n)
    for i in range(n):
        idx = rng.randint(0, len(sums), len(sums))
        boots[i] = sums[idx].sum() / counts[idx].sum()
    return {"diff": float(diff.mean()), "ci_low": float(np.percentile(boots, 2.5)), "ci_high": float(np.percentile(boots, 97.5))}


def calibration_table(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> list[dict]:
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, n_bins - 1)
    rows = []
    for b in range(n_bins):
        m = idx == b
        if m.sum() == 0:
            continue
        rows.append(
            {
                "bin": f"{edges[b]:.1f}-{edges[b + 1]:.1f}",
                "n": int(m.sum()),
                "mean_pred": float(p[m].mean()),
                "mean_actual": float(y[m].mean()),
            }
        )
    return rows


def eval_slice_table(val: pd.DataFrame, y: np.ndarray, preds: dict[str, np.ndarray]) -> list[dict]:
    """Positions with cp in SLICE_CP: same engine eval, broken down by rating band and time class."""
    lo, hi = SLICE_CP
    cp = val["cp_stm_proxy"].to_numpy()
    in_slice = (cp >= lo) & (cp < hi)
    rows = []
    keys = val["rating_band"].astype(str) + " / " + val["time_class"].astype(str)
    for k in sorted(keys[in_slice].unique()):
        m = in_slice & (keys == k).to_numpy()
        if m.sum() < 100:
            continue
        rows.append(
            {
                "group": k,
                "n": int(m.sum()),
                "actual": float(y[m].mean()),
                **{name: float(p[m].mean()) for name, p in preds.items()},
            }
        )
    return rows


def _fmt_pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def render_markdown(report: dict) -> str:
    names = report["model_names"]
    o = report["overall"]
    lines = [
        "# EP model evaluation",
        "",
        f"Held-out: **{report['n_val_rows']:,} positions** from **{report['n_val_games']:,} games** "
        f"(train: {report['n_train_rows']:,} positions). Split by game, so no game appears in both.",
        "",
        "## Overall",
        "",
        "| model | log loss | Brier | MAE | log-loss gain vs Lichess |",
        "|---|---|---|---|---|",
    ]
    base = o["lichess_formula"]["log_loss"]
    for n in names:
        m = o[n]
        gain = (base - m["log_loss"]) / base
        lines.append(f"| {n} | {m['log_loss']:.4f} | {m['brier_clipped']:.4f} | {m['mae']:.4f} | {_fmt_pct(gain)} |")

    lines += ["", "## Paired difference vs ep_model (log loss, 95% CI over games)", "", "| model | difference | 95% CI |", "|---|---|---|"]
    for n, b in report.get("paired_vs_ep_model", {}).items():
        lines.append(f"| {n} | {b['diff']:+.4f} | {b['ci_low']:+.4f} to {b['ci_high']:+.4f} |")

    ref = report.get("paired_vs_reference")
    if ref:
        lines += ["", f"## Paired difference vs {ref['reference']} (log loss, 95% CI over games)", "", "| model | difference | 95% CI |", "|---|---|---|"]
        for n, b in ref["models"].items():
            lines.append(f"| {n} | {b['diff']:+.4f} | {b['ci_low']:+.4f} to {b['ci_high']:+.4f} |")

    for title, key in (("By rating band", "by_rating_band"), ("By time class", "by_time_class")):
        lines += ["", f"## {title} (log loss)", "", "| group | n | " + " | ".join(names) + " |", "|---|---|" + "---|" * len(names)]
        for g, d in report[key].items():
            lines.append(f"| {g} | {d['n']:,} | " + " | ".join(f"{d[n]['log_loss']:.4f}" for n in names) + " |")

    lo, hi = SLICE_CP
    lines += [
        "",
        f"## Same eval, different players (+{lo:.0f} to +{hi:.0f} cp for side to move)",
        "",
        "Mean expected score: what actually happened vs what each model predicted.",
        "",
    ]
    ep_names = [n for n in names if n.startswith("ep_")] + ["lichess_formula"]
    lines += ["| rating / time | n | actual | " + " | ".join(ep_names) + " |", "|---|---|---|" + "---|" * len(ep_names)]
    for r in report["eval_slice"]:
        lines.append(f"| {r['group']} | {r['n']:,} | {_fmt_pct(r['actual'])} | " + " | ".join(_fmt_pct(r[n]) for n in ep_names) + " |")

    lines += ["", "## Calibration (ep_model)", "", "| predicted | n | mean pred | mean actual |", "|---|---|---|---|"]
    for r in report["calibration"]["ep_model"]:
        lines.append(f"| {r['bin']} | {r['n']:,} | {r['mean_pred']:.3f} | {r['mean_actual']:.3f} |")
    return "\n".join(lines) + "\n"


def run(
    processed: Path, models: Path, seed: int, extra_models: dict[str, Path] | None = None, reference: str | None = None
) -> int:
    """reference: also bootstrap every EP model against this one (e.g. the model currently shipped)."""
    model_path = models / "ep_lgbm.txt"
    ids_path = models / "ep_val_game_ids.txt"
    if not model_path.is_file() or not ids_path.is_file():
        LOG.error("Need %s and %s (run phase_c.train first)", model_path, ids_path)
        return 1

    paths = sorted(processed.glob("rows_with_eval_part*.parquet"))
    df, feature_names, target = build_training_frame(load_eval_parquet(paths))
    val_ids = set(ids_path.read_text(encoding="utf-8").split())
    is_val = df["game_id"].astype(str).isin(val_ids)
    train, val = df[~is_val], df[is_val]
    if val.empty:
        LOG.error("No held-out rows found; was the model trained on this data?")
        return 1
    LOG.info("Train rows=%s | Val rows=%s games=%s", len(train), len(val), val["game_id"].nunique())

    y_tr = train[target].to_numpy(dtype=np.float64)
    y = val[target].to_numpy(dtype=np.float64)
    cp_tr = np.clip(train["cp_stm_proxy"].to_numpy(), -CP_CLIP, CP_CLIP)
    cp = np.clip(val["cp_stm_proxy"].to_numpy(), -CP_CLIP, CP_CLIP)

    booster = lgb.Booster(model_file=str(model_path))
    preds: dict[str, np.ndarray] = {"ep_model": booster.predict(val[feature_names])}
    for name, mdir in (extra_models or {}).items():
        preds[name] = lgb.Booster(model_file=str(mdir / "ep_lgbm.txt")).predict(val[feature_names])

    a, b = fit_logistic_1d(cp_tr / 100.0, y_tr)
    LOG.info("eval_logistic: p = sigmoid(%.4f + %.6f * cp)", a, b / 100.0)

    params = {"objective": "cross_entropy", "verbosity": -1, "seed": seed, "num_leaves": 15, "learning_rate": 0.05}
    cp_only = lgb.train(params, lgb.Dataset(train[["cp_stm_proxy"]], label=y_tr), num_boost_round=200)

    preds["eval_lgbm"] = cp_only.predict(val[["cp_stm_proxy"]])
    preds["eval_logistic"] = _sigmoid(a + b * cp / 100.0)
    preds["lichess_formula"] = lichess_expected(val["cp_stm_proxy"].to_numpy())
    preds["constant"] = np.full_like(y, y_tr.mean())

    report = {
        "n_train_rows": int(len(train)),
        "n_val_rows": int(len(val)),
        "n_val_games": int(val["game_id"].nunique()),
        "model_names": list(preds),
        "eval_logistic_params": {"intercept": a, "slope_per_cp": b / 100.0},
        "overall": {n: metrics_regression(y, p) for n, p in preds.items()},
        "by_rating_band": _metrics_by(y, preds, val["rating_band"]),
        "by_time_class": _metrics_by(y, preds, val["time_class"]),
        "eval_slice": eval_slice_table(val, y, preds),
        "calibration": {n: calibration_table(y, preds[n]) for n in ("ep_model", *(extra_models or {}), "lichess_formula")},
        "paired_vs_ep_model": {
            n: paired_bootstrap(y, preds[n], preds["ep_model"], val["game_id"]) for n in preds if n != "ep_model"
        },
    }

    if reference:
        if reference not in preds:
            LOG.error("Unknown --reference %s (have %s)", reference, ", ".join(preds))
            return 1
        report["paired_vs_reference"] = {
            "reference": reference,
            "models": {
                n: paired_bootstrap(y, preds[n], preds[reference], val["game_id"])
                for n in preds
                if n.startswith("ep_") and n != reference
            },
        }
        for n, b in report["paired_vs_reference"]["models"].items():
            LOG.info("%-16s vs %s: %+.4f (95%% CI %+.4f to %+.4f)", n, reference, b["diff"], b["ci_low"], b["ci_high"])

    for n, m in report["overall"].items():
        LOG.info("%-16s log_loss=%.4f brier=%.4f mae=%.4f", n, m["log_loss"], m["brier_clipped"], m["mae"])
    for n, b in report["paired_vs_ep_model"].items():
        LOG.info("%-16s vs ep_model: %+.4f (95%% CI %+.4f to %+.4f)", n, b["diff"], b["ci_low"], b["ci_high"])

    (models / "ep_eval_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (models / "ep_eval_report.md").write_text(render_markdown(report), encoding="utf-8")
    LOG.info("Wrote %s and %s", models / "ep_eval_report.json", models / "ep_eval_report.md")
    return 0


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    p = argparse.ArgumentParser(description="Evaluate EP model vs eval-only baselines on held-out games")
    p.add_argument("--processed-dir", type=Path, default=root / "ep_model" / "processed")
    p.add_argument("--models-dir", type=Path, default=root / "ep_model" / "models")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--extra-model", action="append", default=[], metavar="NAME=DIR", help="Also score this trained model")
    p.add_argument("--reference", default=None, help="Also compare every EP model to this one (paired bootstrap)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    extra = {}
    for spec in args.extra_model:
        name, _, d = spec.partition("=")
        extra[name] = Path(d)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    return run(args.processed_dir, args.models_dir, args.seed, extra, args.reference)


if __name__ == "__main__":
    sys.exit(main())
