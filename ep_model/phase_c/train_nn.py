"""
PyTorch neural-network EP model, trained as a comparison against the LightGBM EP model.

Same features (FEATURE_NAMES), same clock dropout and the same held-out test games as the LightGBM
run in --test-ids-from, so phase_c.evaluate can score both on identical rows. Early stopping uses
an inner split of the training games, never the test games.

Network: embeddings for the categorical features + standardised numeric features -> MLP -> logit,
trained with binary cross-entropy on the soft result (0 / 0.5 / 1).

Usage (repo root):
  python -m ep_model.phase_c.train_nn -v
  python -m ep_model.phase_c.evaluate --extra-nn ep_mlp=ep_model/models_nn -v
  python -m ep_model.phase_c.train_nn predict MODEL_DIR features.parquet pred.npy   (used by evaluate)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn

from ep_model.phase_c.prepare import (
    CATEGORICAL_FEATURES,
    FEATURE_NAMES,
    TRAIN_COLUMNS,
    apply_clock_dropout,
    build_training_frame,
    load_eval_parquet,
    metrics_regression,
    split_game_ids,
)

LOG = logging.getLogger(__name__)

CP_CLIP = 1000.0
LICHESS_K = 0.00368208
# Clock-like features use -1 for "unknown": the network gets log1p(value) plus a missing flag.
CLOCK_FEATURES = ["initial_time_sec", "increment_sec", "clk_stm_sec", "clk_opp_sec"]
NUMERIC_FEATURES = [f for f in FEATURE_NAMES if f not in CATEGORICAL_FEATURES]
MODEL_FILE = "ep_mlp.pt"
META_FILE = "ep_mlp_meta.json"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def numeric_matrix(df: pd.DataFrame) -> np.ndarray:
    """Raw numeric inputs before standardisation; extra columns: Lichess win% of the eval and missing flags."""
    cols = []
    for f in NUMERIC_FEATURES:
        v = df[f].to_numpy(dtype=np.float64)
        if f in ("cp_stm_proxy", "cp_white_proxy"):
            cols.append(np.clip(v, -CP_CLIP, CP_CLIP) / 100.0)
        elif f in CLOCK_FEATURES:
            cols.append(np.log1p(np.maximum(v, 0.0)))
            cols.append((v < 0).astype(np.float64))
        elif f == "clk_stm_frac":
            cols.append(np.clip(v, 0.0, 2.0))
            cols.append((v < 0).astype(np.float64))
        else:
            cols.append(v)
    cp = np.clip(df["cp_stm_proxy"].to_numpy(dtype=np.float64), -CP_CLIP, CP_CLIP)
    cols.append(1.0 / (1.0 + np.exp(-LICHESS_K * cp)))
    return np.column_stack(cols).astype(np.float32)


def category_codes(df: pd.DataFrame, vocab: dict[str, list[str]]) -> np.ndarray:
    """Index 0 is reserved for values not seen in training."""
    out = []
    for c in CATEGORICAL_FEATURES:
        lookup = {v: i + 1 for i, v in enumerate(vocab[c])}
        out.append(df[c].astype(str).map(lookup).fillna(0).to_numpy(dtype=np.int64))
    return np.column_stack(out)


class EPNet(nn.Module):
    def __init__(self, n_numeric: int, cat_sizes: list[int], emb_dim: int = 8, hidden: int = 128, layers: int = 3, dropout: float = 0.1):
        super().__init__()
        self.embs = nn.ModuleList(nn.Embedding(n + 1, min(emb_dim, n + 1)) for n in cat_sizes)
        width = n_numeric + sum(e.embedding_dim for e in self.embs)
        blocks: list[nn.Module] = []
        for _ in range(layers):
            blocks += [nn.Linear(width, hidden), nn.ReLU(), nn.Dropout(dropout)]
            width = hidden
        blocks.append(nn.Linear(width, 1))
        self.mlp = nn.Sequential(*blocks)

    def forward(self, x_num: torch.Tensor, x_cat: torch.Tensor) -> torch.Tensor:
        parts = [x_num] + [e(x_cat[:, i]) for i, e in enumerate(self.embs)]
        return self.mlp(torch.cat(parts, dim=1)).squeeze(1)


class EPNetPredictor:
    """Loads a saved EPNet and predicts expected score for feature frames from build_training_frame."""

    def __init__(self, model_dir: Path):
        meta = json.loads((model_dir / META_FILE).read_text(encoding="utf-8"))
        self.vocab = meta["vocab"]
        self.mean = np.asarray(meta["num_mean"], dtype=np.float32)
        self.std = np.asarray(meta["num_std"], dtype=np.float32)
        self.net = EPNet(len(self.mean), [len(self.vocab[c]) for c in CATEGORICAL_FEATURES], **meta["arch"])
        self.net.load_state_dict(torch.load(model_dir / MODEL_FILE, map_location="cpu"))
        self.net.eval()

    def predict(self, df: pd.DataFrame, batch: int = 65536) -> np.ndarray:
        x_num = torch.from_numpy((numeric_matrix(df) - self.mean) / self.std)
        x_cat = torch.from_numpy(category_codes(df, self.vocab))
        out = []
        with torch.no_grad():
            for i in range(0, len(x_num), batch):
                out.append(torch.sigmoid(self.net(x_num[i : i + batch], x_cat[i : i + batch])).numpy())
        return np.concatenate(out).astype(np.float64) if out else np.empty(0)


def _log_loss(net: EPNet, x_num: torch.Tensor, x_cat: torch.Tensor, y: torch.Tensor) -> float:
    net.eval()
    with torch.no_grad():
        return float(nn.functional.binary_cross_entropy_with_logits(net(x_num, x_cat), y))


def train(
    processed: Path,
    out_dir: Path,
    test_ids_path: Path,
    seed: int = 42,
    clock_dropout: float = 0.15,
    inner_val_fraction: float = 0.1,
    epochs: int = 40,
    patience: int = 4,
    batch_size: int = 1024,
    lr: float = 2e-3,
    arch: dict | None = None,
) -> int:
    arch = {"emb_dim": 8, "hidden": 128, "layers": 3, "dropout": 0.1, **(arch or {})}
    torch.manual_seed(seed)
    paths = sorted(processed.glob("rows_with_eval_part*.parquet"))
    if not paths or not test_ids_path.is_file():
        LOG.error("Need rows_with_eval_part*.parquet in %s and %s", processed, test_ids_path)
        return 1

    df = load_eval_parquet(paths, columns=TRAIN_COLUMNS)
    df = apply_clock_dropout(df, clock_dropout, seed, inplace=True)
    df, _, target = build_training_frame(df, copy=False)
    test_ids = set(test_ids_path.read_text(encoding="utf-8").split())
    train_df = df[~df["game_id"].astype(str).isin(test_ids)]
    fit_ids, stop_ids = split_game_ids(train_df["game_id"].astype(str).unique(), inner_val_fraction, seed)
    is_stop = train_df["game_id"].astype(str).isin(stop_ids)
    fit_df, stop_df = train_df[~is_stop], train_df[is_stop]
    LOG.info("Fit rows=%s games=%s | early-stop rows=%s games=%s (test games excluded: %s)", len(fit_df), len(fit_ids), len(stop_df), len(stop_ids), len(test_ids))

    vocab = {c: sorted(fit_df[c].astype(str).unique().tolist()) for c in CATEGORICAL_FEATURES}
    raw = numeric_matrix(fit_df)
    mean, std = raw.mean(axis=0), raw.std(axis=0) + 1e-6

    def tensors(frame: pd.DataFrame, x: np.ndarray | None = None):
        x = numeric_matrix(frame) if x is None else x
        return (
            torch.from_numpy((x - mean) / std),
            torch.from_numpy(category_codes(frame, vocab)),
            torch.from_numpy(frame[target].to_numpy(dtype=np.float32)),
        )

    xn, xc, y = tensors(fit_df, raw)
    sxn, sxc, sy = tensors(stop_df)

    net = EPNet(xn.shape[1], [len(vocab[c]) for c in CATEGORICAL_FEATURES], **arch)
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, factor=0.5, patience=1)
    best, best_state, bad, history = float("inf"), None, 0, []
    gen = torch.Generator().manual_seed(seed)
    t0 = time.time()
    for epoch in range(1, epochs + 1):
        net.train()
        perm = torch.randperm(len(y), generator=gen)
        for i in range(0, len(y), batch_size):
            idx = perm[i : i + batch_size]
            loss = nn.functional.binary_cross_entropy_with_logits(net(xn[idx], xc[idx]), y[idx])
            opt.zero_grad()
            loss.backward()
            opt.step()
        tr, va = _log_loss(net, xn, xc, y), _log_loss(net, sxn, sxc, sy)
        sched.step(va)
        history.append({"epoch": epoch, "train_log_loss": tr, "stop_log_loss": va})
        LOG.info("epoch %2d train=%.4f early-stop=%.4f (%.0fs)", epoch, tr, va, time.time() - t0)
        if va < best - 1e-5:
            best, bad = va, 0
            best_state = {k: v.clone() for k, v in net.state_dict().items()}
        else:
            bad += 1
            if bad >= patience:
                break

    out_dir.mkdir(parents=True, exist_ok=True)
    torch.save(best_state, out_dir / MODEL_FILE)
    meta = {
        "features": FEATURE_NAMES,
        "vocab": vocab,
        "num_mean": mean.tolist(),
        "num_std": std.tolist(),
        "arch": arch,
        "training": {
            "seed": seed,
            "clock_dropout": clock_dropout,
            "batch_size": batch_size,
            "lr": lr,
            "fit_rows": int(len(fit_df)),
            "early_stop_rows": int(len(stop_df)),
            "best_early_stop_log_loss": best,
            "epochs_run": len(history),
            "seconds": round(time.time() - t0, 1),
            "torch": torch.__version__,
            "n_parameters": int(sum(p.numel() for p in net.parameters())),
        },
        "history": history,
    }
    (out_dir / META_FILE).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (out_dir / "ep_val_game_ids.txt").write_text(test_ids_path.read_text(encoding="utf-8"), encoding="utf-8")
    pred = EPNetPredictor(out_dir).predict(stop_df)
    LOG.info("Saved %s (%s parameters); early-stop metrics %s", out_dir / MODEL_FILE, meta["training"]["n_parameters"], metrics_regression(stop_df[target].to_numpy(), pred))
    return 0


def predict_file(model_dir: Path, features_path: Path, out_path: Path) -> int:
    np.save(out_path, EPNetPredictor(model_dir).predict(pd.read_parquet(features_path)))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["predict"]:
        if len(argv) != 4:
            print("usage: train_nn predict MODEL_DIR FEATURES.parquet OUT.npy", file=sys.stderr)
            return 2
        return predict_file(*(Path(a) for a in argv[1:]))
    root = _repo_root()
    p = argparse.ArgumentParser(description="Train the PyTorch EP model (comparison against LightGBM)")
    p.add_argument("--processed-dir", type=Path, default=root / "ep_model" / "processed")
    p.add_argument("--output-dir", type=Path, default=root / "ep_model" / "models_nn")
    p.add_argument("--test-ids-from", type=Path, default=root / "ep_model" / "models" / "ep_val_game_ids.txt")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--epochs", type=int, default=40)
    p.add_argument("--hidden", type=int, default=128)
    p.add_argument("--layers", type=int, default=3)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    return train(
        args.processed_dir,
        args.output_dir,
        args.test_ids_from,
        seed=args.seed,
        epochs=args.epochs,
        arch={"hidden": args.hidden, "layers": args.layers},
    )


if __name__ == "__main__":
    sys.exit(main())
