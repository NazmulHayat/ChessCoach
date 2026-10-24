"""Feature prep for EP training from Phase B rows."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def mate_to_pseudo_cp(mate: float | int | None) -> float | None:
    """Map mate-in-N (signed, side-to-move POV) to a centipawn-like scale."""
    if mate is None or (isinstance(mate, float) and np.isnan(mate)):
        return None
    m = int(mate)
    sign = 1 if m > 0 else -1
    return float(sign * (10000 - abs(m) * 100))


def cp_or_mate_proxy(cp: float | int | None, mate: float | int | None) -> float:
    """Single numeric score: CP when present, else pseudo-CP from mate, else 0."""
    if mate is not None and not (isinstance(mate, float) and np.isnan(mate)):
        p = mate_to_pseudo_cp(mate)
        return p if p is not None else 0.0
    if cp is not None and not (isinstance(cp, float) and np.isnan(cp)):
        return float(cp)
    return 0.0


def cp_or_mate_proxy_vec(cp: pd.Series, mate: pd.Series) -> np.ndarray:
    """Vectorized cp_or_mate_proxy over whole columns (same rules, row by row)."""
    cp_v = pd.to_numeric(cp, errors="coerce").to_numpy(dtype=np.float64)
    mate_v = pd.to_numeric(mate, errors="coerce").to_numpy(dtype=np.float64)
    mate_cp = np.where(mate_v > 0, 1.0, -1.0) * (10000.0 - np.abs(mate_v) * 100.0)
    return np.where(~np.isnan(mate_v), mate_cp, np.where(~np.isnan(cp_v), cp_v, 0.0))


FEATURE_NAMES = [
    "cp_stm_proxy",
    "cp_white_proxy",
    "elo_to_move",
    "elo_opponent",
    "elo_diff",
    "ply",
    "move_number",
    "side_w",
    "initial_time_sec",
    "increment_sec",
    "clk_stm_sec",
    "clk_opp_sec",
    "clk_stm_frac",
    "phase",
    "time_class",
    "rating_band",
    "opening_eco",
]

CATEGORICAL_FEATURES = ["phase", "time_class", "rating_band", "opening_eco"]


def add_model_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive model feature columns from Phase B-shaped rows (no filtering, no target needed).
    Shared by training and inference so both see identical encodings.
    """
    out = df.copy()

    out["cp_stm_proxy"] = cp_or_mate_proxy_vec(out["eval_cp_stm"], out["mate_stm"])
    out["cp_white_proxy"] = cp_or_mate_proxy_vec(out["eval_cp_white"], out["mate_white"])

    white_to_move = (out["side_to_move"] == "w").to_numpy()
    out["side_w"] = white_to_move.astype(np.int8)

    # Clocks are relative to the side to move. Before a side's first [%clk] comment its clock
    # is still the initial time; otherwise missing means "unknown" (-1), e.g. PGNs without clocks.
    init = pd.to_numeric(out["initial_time_sec"], errors="coerce").to_numpy(dtype=np.float64)
    early = (pd.to_numeric(out["ply"], errors="coerce") <= 2).to_numpy()
    clk = {}
    for col in ("clk_white_sec", "clk_black_sec"):
        v = pd.to_numeric(out[col], errors="coerce").to_numpy(dtype=np.float64)
        clk[col] = np.where(np.isnan(v) & early, init, v)
    stm = np.where(white_to_move, clk["clk_white_sec"], clk["clk_black_sec"])
    opp = np.where(white_to_move, clk["clk_black_sec"], clk["clk_white_sec"])
    with np.errstate(divide="ignore", invalid="ignore"):
        frac = np.where(init > 0, stm / init, np.nan)
    out["clk_stm_sec"] = np.nan_to_num(stm, nan=-1.0)
    out["clk_opp_sec"] = np.nan_to_num(opp, nan=-1.0)
    out["clk_stm_frac"] = np.nan_to_num(frac, nan=-1.0)

    for col in ("initial_time_sec", "increment_sec"):
        out[col] = out[col].fillna(-1).astype(np.int32)

    out["opening_eco"] = out["opening_eco"].fillna("?").astype(str)

    for c in CATEGORICAL_FEATURES:
        out[c] = out[c].astype("category")

    for c in FEATURE_NAMES:
        if c not in out.columns:
            raise KeyError(f"missing column {c}")

    return out


def apply_clock_dropout(df: pd.DataFrame, frac: float, seed: int) -> pd.DataFrame:
    """
    Blank both clocks for a random `frac` of games so the model learns a clock-unknown mode
    (Lichess rows almost always have clocks; many other PGNs do not).
    """
    if frac <= 0:
        return df
    gids = pd.unique(df["game_id"])
    rng = np.random.RandomState(seed)
    drop = set(gids[rng.rand(len(gids)) < frac])
    out = df.copy()
    m = out["game_id"].isin(drop)
    out.loc[m, ["clk_white_sec", "clk_black_sec"]] = np.nan
    return out


def load_eval_parquet(paths: list) -> pd.DataFrame:
    frames = [pd.read_parquet(p) for p in paths]
    return pd.concat(frames, ignore_index=True)


def unique_game_ids_from_parquets(paths: list[Path | str]) -> np.ndarray:
    """Load only `game_id` from each shard (lower peak RAM than full tables)."""
    parts: list[pd.DataFrame] = []
    for p in paths:
        parts.append(pd.read_parquet(p, columns=["game_id"]))
    u = pd.concat(parts, ignore_index=True)["game_id"].unique()
    return np.asarray(u, dtype=object)


def split_game_ids(
    game_ids: np.ndarray | list | pd.Series,
    val_fraction: float,
    seed: int,
) -> tuple[set, set]:
    """Same split logic as split_by_game_id but on unique ids only."""
    gids = list(pd.unique(pd.Series(game_ids)))
    if len(gids) < 2:
        raise ValueError("need at least 2 distinct game_id values for train/val split")
    rng = np.random.RandomState(seed)
    rng.shuffle(gids)
    n_val = max(1, int(len(gids) * val_fraction))
    n_val = min(n_val, len(gids) - 1)
    val_set = set(gids[:n_val])
    train_set = set(gids[n_val:])
    return train_set, val_set


def load_eval_parquet_sharded(
    paths: list[Path | str],
    train_gids: set,
    val_gids: set,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Read one Parquet file at a time, keep only rows whose game_id is in train or val.
    Peak RAM ≈ largest shard + overhead (not full dataset).
    """
    train_parts: list[pd.DataFrame] = []
    val_parts: list[pd.DataFrame] = []
    for p in sorted(Path(x) for x in paths):
        df = pd.read_parquet(p)
        t = df.loc[df["game_id"].isin(train_gids)]
        v = df.loc[df["game_id"].isin(val_gids)]
        if len(t):
            train_parts.append(t)
        if len(v):
            val_parts.append(v)
        del df
    if not train_parts:
        raise ValueError("empty train after sharded load")
    train_df = pd.concat(train_parts, ignore_index=True)
    val_df = pd.concat(val_parts, ignore_index=True) if val_parts else pd.DataFrame()
    if val_df.empty:
        raise ValueError("empty val after sharded load; check val_fraction and data")
    return train_df, val_df


def build_training_frame(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str], str]:
    """
    Returns (Xy_frame with target column 'result_stm', feature_names, target_name).
    Drops rows without an engine eval.
    """
    out = add_model_features(df)
    mask = out["eval_cp_stm"].notna() | out["mate_stm"].notna()
    out = out.loc[mask].copy()
    return out, list(FEATURE_NAMES), "result_stm"


def split_by_game_id(
    df: pd.DataFrame,
    val_fraction: float,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_set, val_set = split_game_ids(df["game_id"].unique(), val_fraction, seed)
    val = df[df["game_id"].isin(val_set)]
    train = df[df["game_id"].isin(train_set)]
    if train.empty:
        raise ValueError("train split empty; lower val_fraction or add more games")
    return train, val


def metrics_regression(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    y_true = np.asarray(y_true, dtype=np.float64)
    y_pred = np.asarray(y_pred, dtype=np.float64)
    mae = float(np.mean(np.abs(y_true - y_pred)))
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    p = np.clip(y_pred, 0.0, 1.0)
    brier = float(np.mean((y_true - p) ** 2))
    # Cross-entropy with soft labels (draw = 0.5); lower is better.
    q = np.clip(y_pred, 1e-6, 1.0 - 1e-6)
    log_loss = float(-np.mean(y_true * np.log(q) + (1.0 - y_true) * np.log(1.0 - q)))
    return {"mae": mae, "rmse": rmse, "brier_clipped": brier, "log_loss": log_loss}


def metrics_by_rating_band(y_true: np.ndarray, y_pred: np.ndarray, bands: pd.Series) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for b in bands.unique():
        m = bands == b
        if m.sum() < 5:
            continue
        out[str(b)] = metrics_regression(y_true[m.values], y_pred[m.values])
    return out
