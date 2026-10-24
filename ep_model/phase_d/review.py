"""
Review a PGN move by move with Stockfish + the EP model.

For each move: the mover's expected score (EP) had they played the engine's best move, EP after the
move actually played, the difference (EP loss), and a label from EP loss. Both EPs are scored on an
opponent-to-move row with identical context, so any side-to-move bias in the model cancels out.
The same thresholds applied to the Lichess win% curve give the eval-only label for comparison.

Usage (repo root):
  python -m ep_model.phase_d.review game.pgn
  python -m ep_model.phase_d.review game.pgn --white-elo 1450 --black-elo 1500 --depth 14 --html out.html
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import chess
import chess.engine
import chess.pgn

from ep_model.phase_a.rowgen import (
    classify_time_class,
    collect_mainline_moves,
    game_phase_from_half_moves,
    parse_clock_comment,
    parse_clock_header,
    parse_time_control,
    rating_band_from_average,
)
from ep_model.phase_b.augment_evals import load_policy
from ep_model.phase_b.eval_extract import extract_eval_fields
from ep_model.phase_c.evaluate import lichess_expected
from ep_model.phase_c.prepare import cp_or_mate_proxy
from ep_model.phase_d.predictor import EPModel

LOG = logging.getLogger(__name__)

# Expected-score drop thresholds (0-1 scale). Same cut-offs for EP and the Lichess curve,
# so label differences come from the model, not the thresholds.
LABELS = [(0.02, "excellent"), (0.05, "good"), (0.10, "inaccuracy"), (0.15, "mistake")]
WORST_LABEL = "blunder"


def label_for_loss(loss: float, is_engine_best: bool) -> str:
    if is_engine_best:
        return "best"
    for limit, name in LABELS:
        if loss < limit:
            return name
    return WORST_LABEL


def _elo(headers: chess.pgn.Headers, key: str, override: int | None) -> int:
    if override is not None:
        return override
    raw = headers.get(key, "")
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(f"PGN has no usable {key}; pass --{key[:5].lower()}-elo") from None


def _terminal_score(board: chess.Board) -> float | None:
    """Expected score for the side to move when the game is over on the board."""
    if board.is_checkmate():
        return 0.0
    if board.is_game_over(claim_draw=True):
        return 0.5
    return None


def best_move_row(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """
    Counterfactual opponent-to-move row for "mover played the engine's best move": the context of
    the real position after the move (ply, clocks, side), with the eval carried over from before.
    """
    row = dict(after)
    cp, mate = before["eval_cp_stm"], before["mate_stm"]
    row["terminal"] = None
    if mate is not None:
        if mate > 0:
            # Mover mates in N: after the best move the opponent is mated in N-1.
            row["eval_cp_stm"], row["mate_stm"] = None, -(mate - 1)
            if mate == 1:
                row["terminal"] = 0.0
        else:
            row["eval_cp_stm"], row["mate_stm"] = None, -mate
    else:
        row["eval_cp_stm"], row["mate_stm"] = (-cp if cp is not None else None), None
    white_to_move = row["side_to_move"] == "w"
    sign = 1 if white_to_move else -1
    row["eval_cp_white"] = sign * row["eval_cp_stm"] if row["eval_cp_stm"] is not None else None
    row["mate_white"] = sign * row["mate_stm"] if row["mate_stm"] is not None else None
    return row


def review_game(
    game: chess.pgn.Game,
    model: EPModel,
    engine: chess.engine.SimpleEngine,
    depth: int,
    white_elo: int | None = None,
    black_elo: int | None = None,
) -> dict[str, Any]:
    h = game.headers
    w_elo = _elo(h, "WhiteElo", white_elo)
    b_elo = _elo(h, "BlackElo", black_elo)
    init, inc = parse_time_control(h.get("TimeControl"))
    time_class = classify_time_class(init)
    band = rating_band_from_average((w_elo + b_elo) / 2.0)
    eco = h.get("ECO") or None

    nodes = collect_mainline_moves(game)
    board = game.board()
    clk_w = parse_clock_header(h.get("WhiteClock"))
    clk_b = parse_clock_header(h.get("BlackClock"))

    # One row per position (before each move, plus the final position), Phase A/B field names.
    positions: list[dict[str, Any]] = []
    for i in range(len(nodes) + 1):
        info = engine.analyse(board, chess.engine.Limit(depth=depth))
        white_to_move = board.turn == chess.WHITE
        elo_to_move, elo_opp = (w_elo, b_elo) if white_to_move else (b_elo, w_elo)
        pv = info.get("pv") or []
        positions.append(
            {
                "fen": board.fen(),
                "best_move_uci": pv[0].uci() if pv else None,
                "best_move_san": board.san(pv[0]) if pv else None,
                "terminal": _terminal_score(board),
                "ply": i + 1,
                "move_number": board.fullmove_number,
                "side_to_move": "w" if white_to_move else "b",
                "white_elo": w_elo,
                "black_elo": b_elo,
                "elo_to_move": elo_to_move,
                "elo_opponent": elo_opp,
                "elo_diff": elo_to_move - elo_opp,
                "time_class": time_class,
                "initial_time_sec": init,
                "increment_sec": inc,
                "clk_white_sec": clk_w,
                "clk_black_sec": clk_b,
                "phase": game_phase_from_half_moves(len(board.move_stack)),
                "opening_eco": eco,
                "rating_band": band,
                **extract_eval_fields(board, info),
            }
        )
        if i == len(nodes):
            break
        node = nodes[i]
        clk_after = parse_clock_comment(node.comment)
        board.push(node.move)
        if clk_after is not None:
            if board.turn == chess.BLACK:
                clk_w = clk_after
            else:
                clk_b = clk_after
        LOG.debug("analysed ply %s/%s", i + 1, len(nodes))

    ep = model.predict_rows(positions)
    for pos, e in zip(positions, ep):
        cp = cp_or_mate_proxy(pos["eval_cp_stm"], pos["mate_stm"])
        pos["ep_stm"] = pos["terminal"] if pos["terminal"] is not None else float(e)
        pos["lichess_stm"] = pos["terminal"] if pos["terminal"] is not None else float(lichess_expected(cp))
        pos["cp_stm"] = cp

    best_rows = [best_move_row(positions[i], positions[i + 1]) for i in range(len(nodes))]
    best_ep = model.predict_rows(best_rows)

    moves: list[dict[str, Any]] = []
    board = game.board()
    for i, node in enumerate(nodes):
        before, after = positions[i], positions[i + 1]
        san = board.san(node.move)
        mover = "white" if board.turn == chess.WHITE else "black"
        board.push(node.move)
        is_best = node.move.uci() == before["best_move_uci"]
        # Mover's point of view: after the move it is the opponent to move, so flip.
        b = best_rows[i]
        ep_best = 1.0 - (b["terminal"] if b["terminal"] is not None else float(best_ep[i]))
        ep_after = 1.0 - after["ep_stm"]
        li_best, li_after = before["lichess_stm"], 1.0 - after["lichess_stm"]
        ep_loss = 0.0 if is_best else max(0.0, ep_best - ep_after)
        li_loss = 0.0 if is_best else max(0.0, li_best - li_after)
        moves.append(
            {
                "ply": i + 1,
                "move_number": before["move_number"],
                "mover": mover,
                "san": san,
                "best_san": before["best_move_san"],
                "cp_before": before["cp_stm"],
                "ep_best": ep_best,
                "ep_after": ep_after,
                "ep_loss": ep_loss,
                "ep_label": label_for_loss(ep_loss, is_best),
                "lichess_best": li_best,
                "lichess_after": li_after,
                "lichess_loss": li_loss,
                "lichess_label": label_for_loss(li_loss, is_best),
                "clock_sec": before["clk_white_sec"] if mover == "white" else before["clk_black_sec"],
            }
        )

    summary: dict[str, Any] = {}
    for side in ("white", "black"):
        mine = [m for m in moves if m["mover"] == side]
        counts: dict[str, int] = {}
        for m in mine:
            counts[m["ep_label"]] = counts.get(m["ep_label"], 0) + 1
        summary[side] = {
            "moves": len(mine),
            "avg_ep_loss": sum(m["ep_loss"] for m in mine) / len(mine) if mine else 0.0,
            "labels": counts,
        }

    return {
        "headers": dict(h),
        "white_elo": w_elo,
        "black_elo": b_elo,
        "time_class": time_class,
        "rating_band": band,
        "engine_depth": depth,
        "white_ep_by_ply": [p["ep_stm"] if p["side_to_move"] == "w" else 1.0 - p["ep_stm"] for p in positions],
        "white_lichess_by_ply": [p["lichess_stm"] if p["side_to_move"] == "w" else 1.0 - p["lichess_stm"] for p in positions],
        "moves": moves,
        "summary": summary,
    }


def print_review(r: dict[str, Any]) -> None:
    h = r["headers"]
    print(f"{h.get('White', '?')} ({r['white_elo']}) vs {h.get('Black', '?')} ({r['black_elo']})  "
          f"{h.get('Result', '*')}  {r['time_class']}  depth {r['engine_depth']}")
    print(f"{'move':<14}{'EP best':>10}{'EP after':>10}{'EP loss':>9}  {'EP label':<12}{'eval-only':<12}best")
    for m in r["moves"]:
        num = f"{m['move_number']}{'.' if m['mover'] == 'white' else '...'}"
        flag = " *" if m["ep_label"] != m["lichess_label"] else ""
        print(
            f"{num + ' ' + m['san']:<14}{m['ep_best']:>10.1%}{m['ep_after']:>10.1%}{m['ep_loss']:>9.1%}  "
            f"{m['ep_label']:<12}{m['lichess_label']:<12}{m['best_san'] or ''}{flag}"
        )
    for side, s in r["summary"].items():
        print(f"{side}: avg EP loss {s['avg_ep_loss']:.1%} | {s['labels']}")
    print("* = EP label differs from the eval-only (Lichess curve) label")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Phase D: EP-based move review for one PGN")
    p.add_argument("pgn", type=Path)
    p.add_argument("--game-index", type=int, default=0, help="Which game in the file (0-based)")
    p.add_argument("--white-elo", type=int, default=None)
    p.add_argument("--black-elo", type=int, default=None)
    p.add_argument("--policy", type=Path, default=Path(__file__).resolve().parents[1] / "config" / "engine_policy.json")
    p.add_argument("--depth", type=int, default=None, help="Override policy depth (model was trained at policy depth)")
    p.add_argument("--model-dir", type=Path, default=None)
    p.add_argument("--json", type=Path, default=None, help="Write full review JSON here")
    p.add_argument("--html", type=Path, default=None, help="Write an HTML report here")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")

    with open(args.pgn, encoding="utf-8") as f:
        for _ in range(args.game_index):
            if chess.pgn.read_game(f) is None:
                break
        game = chess.pgn.read_game(f)
    if game is None:
        LOG.error("No game at index %s in %s", args.game_index, args.pgn)
        return 1

    policy = load_policy(args.policy)
    depth = args.depth or int(policy["depth"])
    model = EPModel(args.model_dir)
    engine = chess.engine.SimpleEngine.popen_uci(policy.get("stockfish_path", "stockfish"))
    try:
        engine.configure({"Threads": int(policy.get("threads", 1)), "Hash": int(policy.get("hash_mb", 64))})
        result = review_game(game, model, engine, depth, args.white_elo, args.black_elo)
    finally:
        engine.quit()

    print_review(result)
    if args.json:
        args.json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if args.html:
        from ep_model.phase_d.report_html import render_html

        args.html.write_text(render_html(result), encoding="utf-8")
        LOG.info("Wrote %s", args.html)
    return 0


if __name__ == "__main__":
    sys.exit(main())
