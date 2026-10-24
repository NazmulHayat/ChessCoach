"""
Safe overnight / background Phase B runner: small batches, cooldowns, health checks, resume.

Design goals:
  - Do not melt the laptop: lower nice, optional background engine policy, rest between batches.
  - Survive interrupts: Phase B --resume + Parquet shards + checkpoint DB (unchanged).
  - Bounded disk: stop if processed dir or free space crosses limits.
  - Clean progress: one status line per batch + JSON state; child uses --quiet.

Usage (repo root, venv active):
  python -m ep_model.scripts.safe_run
  python -m ep_model.scripts.safe_run --dry-run

Requires: psutil (see requirements.txt)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

LOG = logging.getLogger("safe_run")

try:
    import psutil
except ImportError as e:
    raise SystemExit(
        "safe_run requires psutil: pip install psutil"
    ) from e


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass
class HealthSnapshot:
    disk_free_gib: float
    swap_used_gib: float
    mem_percent: float
    processed_dir_gib: float
    therm_hint: str


def _disk_free_gib(path: str = "/") -> float:
    return psutil.disk_usage(path).free / (1024**3)


def _dir_size_gib(path: Path) -> float:
    total = 0
    if not path.is_dir():
        return 0.0
    for f in path.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return total / (1024**3)


def _swap_used_gib() -> float:
    return psutil.swap_memory().used / (1024**3)


def _therm_hint() -> str:
    try:
        r = subprocess.run(
            ["pmset", "-g", "therm"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        t = (r.stdout or "").strip().replace("\n", " ")
        return t[:200] if t else "n/a"
    except (OSError, subprocess.TimeoutExpired):
        return "n/a"


def snapshot(processed_dir: Path, disk_path: str) -> HealthSnapshot:
    return HealthSnapshot(
        disk_free_gib=_disk_free_gib(disk_path),
        swap_used_gib=_swap_used_gib(),
        mem_percent=psutil.virtual_memory().percent,
        processed_dir_gib=_dir_size_gib(processed_dir),
        therm_hint=_therm_hint(),
    )


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(path)


def build_phase_b_command(
    repo_root: Path,
    batch_rows: int,
    flush_rows: int,
    policy: Path,
    summary_json: Path,
    nice: int,
) -> list[str]:
    mod = [
        sys.executable,
        "-m",
        "ep_model.phase_b.augment_evals",
        "--input-dir",
        str(repo_root / "ep_model" / "processed"),
        "--out-dir",
        str(repo_root / "ep_model" / "processed"),
        "--policy",
        str(policy),
        "--cache-db",
        str(repo_root / "ep_model" / "processed" / "fen_eval_cache.sqlite"),
        "--checkpoint-db",
        str(repo_root / "ep_model" / "processed" / "phase_b_row_checkpoint.sqlite"),
        "--resume",
        "--quiet",
        "--max-rows",
        str(batch_rows),
        "--flush-rows",
        str(flush_rows),
        "--summary-json",
        str(summary_json),
    ]
    if os.name != "nt" and nice != 0:
        return ["nice", "-n", str(nice)] + mod
    return mod


def run_loop(cfg: argparse.Namespace) -> int:
    repo = _repo_root()
    processed = repo / "ep_model" / "processed"
    state_path = processed / "safe_run_state.json"
    summary_path = processed / "phase_b_last_summary.json"
    log_path = processed / "safe_run_phase_b.log"

    os.chdir(repo)
    proc_env = os.environ.copy()
    proc_env.setdefault("PYTHONUNBUFFERED", "1")

    state = _load_json(state_path)
    if not state.get("started_utc"):
        state["started_utc"] = datetime.now(timezone.utc).isoformat()
    state.setdefault("batches_completed", 0)
    state.setdefault("total_rows_written_session", 0)
    state.setdefault("total_engine_calls_session", 0)

    t_start = time.perf_counter()
    max_sec = float(cfg.max_wall_hours) * 3600.0
    disk_path = cfg.disk_path

    LOG.info(
        "safe_run | processed_dir_budget≤%.1fGiB free≥%.1fGiB | wall≤%.1fh | batch=%s rows cooldown=%ss nice=%s",
        cfg.max_processed_gib,
        cfg.min_free_gib,
        cfg.max_wall_hours,
        cfg.batch_rows,
        cfg.cooldown_sec,
        cfg.nice,
    )

    batch_idx = 0
    while True:
        elapsed_h = (time.perf_counter() - t_start) / 3600.0
        if elapsed_h >= cfg.max_wall_hours:
            LOG.warning("Wall budget reached (%.2fh). Stopping; Phase B is resumable.", elapsed_h)
            state["stopped_reason"] = "wall_budget"
            _save_json(state_path, state)
            return 0

        h = snapshot(processed, disk_path)
        if h.disk_free_gib < cfg.min_free_gib:
            LOG.error(
                "Disk free %.1fGiB < min %.1fGiB — stop (free space). Resume later after cleanup.",
                h.disk_free_gib,
                cfg.min_free_gib,
            )
            state["stopped_reason"] = "min_free_disk"
            state["last_health"] = asdict(h)
            _save_json(state_path, state)
            return 2
        if h.processed_dir_gib > cfg.max_processed_gib:
            LOG.error(
                "ep_model/processed ≈ %.1fGiB > max %.1fGiB — stop (disk budget).",
                h.processed_dir_gib,
                cfg.max_processed_gib,
            )
            state["stopped_reason"] = "processed_dir_budget"
            state["last_health"] = asdict(h)
            _save_json(state_path, state)
            return 3
        if cfg.max_swap_gib > 0 and h.swap_used_gib > cfg.max_swap_gib:
            LOG.error(
                "Swap used %.1fGiB > max %.1fGiB — stop (memory pressure). Retry with lower Stockfish Hash/Threads.",
                h.swap_used_gib,
                cfg.max_swap_gib,
            )
            state["stopped_reason"] = "swap_limit"
            state["last_health"] = asdict(h)
            _save_json(state_path, state)
            return 4

        if (
            cfg.max_total_new_rows > 0
            and state["total_rows_written_session"] >= cfg.max_total_new_rows
        ):
            LOG.warning(
                "Row budget reached (%s new rows this session). Stopping.",
                state["total_rows_written_session"],
            )
            state["stopped_reason"] = "row_budget"
            _save_json(state_path, state)
            return 0

        batch_idx += 1
        cmd = build_phase_b_command(
            repo,
            batch_rows=cfg.batch_rows,
            flush_rows=cfg.flush_rows,
            policy=Path(cfg.policy),
            summary_json=summary_path,
            nice=cfg.nice,
        )

        if cfg.dry_run:
            LOG.info("DRY RUN cmd: %s", " ".join(cmd))
            return 0

        LOG.info(
            "━━ batch %s | session_rows=%s | elapsed=%.2fh/%.1fh | free_disk=%.1fGiB processed≈%.1fGiB swap=%.2fGiB mem=%.0f%% ━━",
            batch_idx,
            state["total_rows_written_session"],
            elapsed_h,
            cfg.max_wall_hours,
            h.disk_free_gib,
            h.processed_dir_gib,
            h.swap_used_gib,
            h.mem_percent,
        )

        t0 = time.perf_counter()
        with open(log_path, "a", encoding="utf-8") as logf:
            logf.write(f"\n--- batch {batch_idx} {datetime.now(timezone.utc).isoformat()} ---\n")
            logf.flush()
            rc = subprocess.run(
                cmd,
                cwd=repo,
                env=proc_env,
                stdout=subprocess.DEVNULL,
                stderr=logf,
            ).returncode

        batch_sec = time.perf_counter() - t0
        if rc != 0:
            LOG.error("Phase B exited with code %s (see %s)", rc, log_path)
            state["stopped_reason"] = f"phase_b_exit_{rc}"
            _save_json(state_path, state)
            return rc

        summ = _load_json(summary_path)
        written = int(summ.get("rows_written", 0))
        skipped = int(summ.get("rows_skipped_done", 0))
        ecs = int(summ.get("engine_calls", 0))
        no_pending = bool(summ.get("no_pending_work", False))
        limit_hit = bool(summ.get("batch_limit_hit", False))

        state["batches_completed"] = int(state["batches_completed"]) + 1
        state["total_rows_written_session"] = int(state["total_rows_written_session"]) + written
        state["total_engine_calls_session"] = int(state["total_engine_calls_session"]) + ecs
        state["last_batch_elapsed_sec"] = round(batch_sec, 3)
        state["last_summary"] = summ
        state["last_health_after_batch"] = asdict(snapshot(processed, disk_path))
        _save_json(state_path, state)

        eta_h = None
        if written > 0 and cfg.max_total_new_rows > 0:
            left = cfg.max_total_new_rows - state["total_rows_written_session"]
            if left > 0:
                eta_h = (left / written) * (batch_sec / 3600.0)

        LOG.info(
            "batch %s done | wrote=%s skipped=%s engine_calls=%s | batch=%.1fs | no_pending_work=%s limit_hit=%s | session_rows=%s%s",
            batch_idx,
            written,
            skipped,
            ecs,
            batch_sec,
            no_pending,
            limit_hit,
            state["total_rows_written_session"],
            f" | rough_eta_row_budget={eta_h:.2f}h" if eta_h is not None else "",
        )

        if no_pending:
            LOG.info("Phase B has no pending rows (all Phase A rows already augmented). Done.")
            state["stopped_reason"] = "phase_b_complete"
            _save_json(state_path, state)
            return 0

        if cfg.cooldown_sec > 0:
            LOG.info("Cooling down %ss before next batch…", cfg.cooldown_sec)
            time.sleep(float(cfg.cooldown_sec))

    return 0


def main(argv: list[str] | None = None) -> int:
    repo = _repo_root()
    proc = repo / "ep_model" / "processed"
    default_policy = repo / "ep_model" / "config" / "engine_policy_background.json"

    p = argparse.ArgumentParser(
        description="Safe batched Phase B with health checks, cooldowns, and resume."
    )
    p.add_argument(
        "--policy",
        type=Path,
        default=default_policy,
        help="Stockfish policy JSON (default: engine_policy_background.json — cooler)",
    )
    p.add_argument("--batch-rows", type=int, default=20_000, help="Max new rows per Stockfish run")
    p.add_argument("--flush-rows", type=int, default=10_000, help="Parquet shard size (same as Phase B)")
    p.add_argument("--cooldown-sec", type=int, default=120, help="Pause between batches (0 = none)")
    p.add_argument("--nice", type=int, default=15, help="Unix nice level for Phase B (0 = disabled on Unix)")
    p.add_argument("--max-wall-hours", type=float, default=30.0, help="Stop after this wall time (orchestrator only)")
    p.add_argument(
        "--max-processed-gib",
        type=float,
        default=130.0,
        help="Stop if ep_model/processed total size exceeds this (approx)",
    )
    p.add_argument(
        "--min-free-gib",
        type=float,
        default=15.0,
        help="Stop if free disk space falls below this (GiB)",
    )
    p.add_argument(
        "--max-swap-gib",
        type=float,
        default=6.0,
        help="Stop if swap used exceeds this (0 = disable check)",
    )
    p.add_argument(
        "--max-total-new-rows",
        type=int,
        default=0,
        help="Stop after this many new rows written this session (0 = unlimited)",
    )
    p.add_argument("--disk-path", type=str, default="/", help="Volume for free-space check")
    p.add_argument("--dry-run", action="store_true", help="Print one command and exit")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )

    if not args.policy.is_file():
        LOG.error("Policy not found: %s", args.policy)
        return 1

    proc.mkdir(parents=True, exist_ok=True)
    return run_loop(args)


if __name__ == "__main__":
    sys.exit(main())
