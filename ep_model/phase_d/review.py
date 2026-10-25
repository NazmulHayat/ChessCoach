"""
Review a PGN move by move with Stockfish + the EP model.

For each move: the mover's expected score (EP) had they played the engine's best move, EP after the
move actually played, the difference (EP loss), and a label from EP loss. Both EPs are scored on an
opponent-to-move row with identical context, so any side-to-move bias in the model cancels out.
The same thresholds applied to the Lichess win% curve give the eval-only label for comparison.

Labels follow Chess.com's published expected-points bands (Classification V2): best = engine move,
excellent < 0.02, good < 0.05, inaccuracy < 0.10, mistake < 0.20, blunder >= 0.20, plus book moves.
Great / Miss / Brilliant are our own rules on top (special.py); they need the engine's second line.

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
from typing import Any, Callable

import chess
import chess.pgn
import chess.polyglot

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
from ep_model.phase_c.evaluate import lichess_expected
from ep_model.phase_c.prepare import cp_or_mate_proxy
from ep_model.phase_d.predictor import EPModel
from ep_model.phase_d.accuracy import combine, ep_move_weights, move_accuracy_pct
from ep_model.phase_d.rating_estimate import estimate_rating, phase_grade, phase_of
from ep_model.phase_d.ratings import detect_pool, from_lichess_scale, to_lichess_scale
from ep_model.phase_d.special import is_brilliant, is_great, is_miss, sacrifice_points, sacrificed_piece, thresholds_for
from ep_model.phase_d.tactics import tactic_hint

LOG = logging.getLogger(__name__)

DEFAULT_BOOK = Path(__file__).resolve().parent / "data" / "book.bin"
BOOK_MAX_PLY = 30

# Expected-score drop thresholds (0-1 scale), Chess.com's bands. Same cut-offs for EP and the
# Lichess curve, so label differences come from the model, not the thresholds.
LABELS = [(0.02, "excellent"), (0.05, "good"), (0.10, "inaccuracy"), (0.20, "mistake")]
WORST_LABEL = "blunder"

# Labels that mean "you lost something here": retry mode, key moments, best-move arrow.
BAD_LABELS = ("inaccuracy", "mistake", "blunder", "miss")

# fens, progress(done, total) -> eval fields + best_uci per FEN (see EnginePool.analyse)
AnalyseFn = Callable[[list[str], Callable[[int, int], None] | None], list[dict[str, Any]]]


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
        raise ValueError(f"PGN has no usable {key}; pass it explicitly") from None


def _terminal_score(board: chess.Board) -> float | None:
    """Expected score for the side to move when the game is over on the board."""
    if board.is_checkmate():
        return 0.0
    if board.is_game_over(claim_draw=True):
        return 0.5
    return None


def _with_white_fields(row: dict[str, Any]) -> dict[str, Any]:
    sign = 1 if row["side_to_move"] == "w" else -1
    row["eval_cp_white"] = sign * row["eval_cp_stm"] if row["eval_cp_stm"] is not None else None
    row["mate_white"] = sign * row["mate_stm"] if row["mate_stm"] is not None else None
    return row


def best_move_row(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """
    Counterfactual opponent-to-move row for "mover played the engine's best move": the context of
    the real position after the move (ply, clocks, side), with the eval carried over from before.
    """
    return counterfactual_row(after, before["eval_cp_stm"], before["mate_stm"])


def counterfactual_row(after: dict[str, Any], cp: int | None, mate: int | None) -> dict[str, Any]:
    """`after`'s context with the opponent to move, scored as if the mover's move had eval (cp, mate) for them."""
    row = dict(after)
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
    return _with_white_fields(row)


def _san_line(fen: str, ucis: list[str]) -> list[str]:
    b = chess.Board(fen)
    out = []
    for u in ucis:
        mv = chess.Move.from_uci(u)
        if mv not in b.legal_moves:
            break
        out.append(b.san(mv))
        b.push(mv)
    return out


def mirrored_row(row: dict[str, Any]) -> dict[str, Any]:
    """The same position and white-POV eval, scored as if the other side were to move."""
    m = dict(row)
    m["side_to_move"] = "b" if row["side_to_move"] == "w" else "w"
    m["elo_to_move"], m["elo_opponent"] = row["elo_opponent"], row["elo_to_move"]
    m["elo_diff"] = -row["elo_diff"]
    m["eval_cp_stm"] = -row["eval_cp_stm"] if row["eval_cp_stm"] is not None else None
    m["mate_stm"] = -row["mate_stm"] if row["mate_stm"] is not None else None
    return m


def review_game(
    game: chess.pgn.Game,
    model: EPModel,
    analyse: AnalyseFn,
    depth: int,
    white_elo: int | None = None,
    black_elo: int | None = None,
    rating_pool: str = "auto",
    book_path: Path | None = DEFAULT_BOOK,
    progress: Callable[[int, int], None] | None = None,
    keep_rows: bool = False,
) -> dict[str, Any]:
    """
    Full review: per-move labels, summary, display series. keep_rows=True adds "_rows" (the model rows per
    position), which score_attempt needs to judge a move tried in retry mode; strip it before sending.
    """
    h = game.headers
    w_elo_raw = _elo(h, "WhiteElo", white_elo)
    b_elo_raw = _elo(h, "BlackElo", black_elo)
    init, inc = parse_time_control(h.get("TimeControl"))
    time_class = classify_time_class(init)
    pool = detect_pool(dict(h)) if rating_pool == "auto" else rating_pool
    w_elo = to_lichess_scale(w_elo_raw, pool, time_class)
    b_elo = to_lichess_scale(b_elo_raw, pool, time_class)
    band = rating_band_from_average((w_elo + b_elo) / 2.0)
    eco = h.get("ECO") or None

    nodes = collect_mainline_moves(game)
    board = game.board()
    start_fen = board.fen()
    clk_w = parse_clock_header(h.get("WhiteClock"))
    clk_b = parse_clock_header(h.get("BlackClock"))

    # One row per position (before each move, plus the final position), Phase A/B field names.
    positions: list[dict[str, Any]] = []
    for i in range(len(nodes) + 1):
        white_to_move = board.turn == chess.WHITE
        elo_to_move, elo_opp = (w_elo, b_elo) if white_to_move else (b_elo, w_elo)
        positions.append(
            {
                "fen": board.fen(),
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

    evals = analyse([p["fen"] for p in positions], progress)
    for pos, ev in zip(positions, evals):
        pos.update({k: ev[k] for k in ("eval_cp_white", "mate_white", "eval_cp_stm", "mate_stm", "eval_depth")})
        b = chess.Board(pos["fen"])
        best = chess.Move.from_uci(ev["best_uci"]) if ev.get("best_uci") else None
        pos["best_uci"] = best.uci() if best else None
        pos["best_san"] = b.san(best) if best else None
        pos["best_line_san"] = _san_line(pos["fen"], ev.get("pv_uci") or [])
        second = chess.Move.from_uci(ev["second_uci"]) if ev.get("second_uci") else None
        pos["second_uci"] = second.uci() if second else None
        pos["second_san"] = b.san(second) if second else None
        pos["second_cp_stm"], pos["second_mate_stm"] = ev.get("second_cp_stm"), ev.get("second_mate_stm")

    ep = model.predict_rows(positions)
    ep_mirror = model.predict_rows([mirrored_row(p) for p in positions])
    for pos, e, em in zip(positions, ep, ep_mirror):
        cp = cp_or_mate_proxy(pos["eval_cp_stm"], pos["mate_stm"])
        pos["cp_stm"] = cp
        if pos["terminal"] is not None:
            pos["ep_stm"] = pos["lichess_stm"] = pos["terminal"]
            stm_white = pos["side_to_move"] == "w"
            pos["white_ep_display"] = pos["terminal"] if stm_white else 1.0 - pos["terminal"]
        else:
            pos["ep_stm"] = float(e)
            pos["lichess_stm"] = float(lichess_expected(cp))
            # Display value (eval bar, graph): average of the side-to-move view and the mirrored view,
            # so the curve doesn't zig-zag with whoever happens to be on move.
            white_view = float(e) if pos["side_to_move"] == "w" else 1.0 - float(e)
            mirror_white_view = 1.0 - float(em) if pos["side_to_move"] == "w" else float(em)
            pos["white_ep_display"] = 0.5 * (white_view + mirror_white_view)

    best_rows = [best_move_row(positions[i], positions[i + 1]) for i in range(len(nodes))]
    best_ep = model.predict_rows(best_rows)
    # Second-best move, same counterfactual construction (mover's EP had they played it).
    second_idx = [i for i in range(len(nodes)) if positions[i]["second_uci"]]
    second_rows = [
        counterfactual_row(positions[i + 1], positions[i]["second_cp_stm"], positions[i]["second_mate_stm"]) for i in second_idx
    ]
    second_pred = model.predict_rows(second_rows)
    ep_second_by_ply: dict[int, float] = {}
    for i, row, e in zip(second_idx, second_rows, second_pred):
        ep_second_by_ply[i] = 1.0 - (row["terminal"] if row["terminal"] is not None else float(e))

    book = None
    if book_path is not None and Path(book_path).is_file():
        book = chess.polyglot.open_reader(str(book_path))
    in_book = book is not None

    moves: list[dict[str, Any]] = []
    board = game.board()
    try:
        for i, node in enumerate(nodes):
            before, after = positions[i], positions[i + 1]
            mv = node.move
            san = board.san(mv)
            mover = "white" if board.turn == chess.WHITE else "black"
            is_book = False
            if in_book and i < BOOK_MAX_PLY:
                is_book = any(e.move == mv for e in book.find_all(board))
            in_book = in_book and is_book
            phase = phase_of(board, i + 1, is_book)
            legal_count = board.legal_moves.count()
            prev = moves[-1] if moves else None
            is_recapture = (
                prev is not None and prev["capture"] and mv.to_square == chess.parse_square(prev["to"]) and board.is_capture(mv)
            )
            is_capture = board.is_capture(mv)
            board_before = board.copy(stack=False)
            board.push(mv)
            is_best = mv.uci() == before["best_uci"]
            # Mover's point of view: after the move it is the opponent to move, so flip.
            bst = best_rows[i]
            ep_best = 1.0 - (bst["terminal"] if bst["terminal"] is not None else float(best_ep[i]))
            ep_after = 1.0 - after["ep_stm"]
            li_best, li_after = before["lichess_stm"], 1.0 - after["lichess_stm"]
            ep_loss = 0.0 if (is_best or is_book) else max(0.0, ep_best - ep_after)
            li_loss = 0.0 if (is_best or is_book) else max(0.0, li_best - li_after)
            base_label = "book" if is_book else label_for_loss(ep_loss, is_best)
            ep_second = ep_second_by_ply.get(i)
            mover_elo = before["elo_to_move"]
            special = None
            sac, sac_piece = 0, None
            if not is_book:
                # Brilliant: alternative = the second line if this was the best move, else the best move.
                alt = ep_second if is_best else ep_best
                if ep_loss <= thresholds_for(mover_elo).brilliant_max_loss:
                    sac = sacrifice_points(board_before, mv)
                if is_brilliant(ep_loss, ep_after, alt, mover_elo, sac):
                    special = "brilliant"
                    sac_piece = sacrificed_piece(board_before, mv)
                elif is_great(is_best, ep_best, ep_second, mover_elo, legal_count, is_recapture, board.is_checkmate()):
                    special = "great"
                elif prev is not None and is_miss(
                    is_best, ep_loss, ep_after, prev["ep_loss"], 1.0 - prev["ep_best"]
                ):
                    special = "miss"
            ep_label = special or base_label
            tactic = (
                tactic_hint(before["fen"], mv.uci(), before["best_uci"], before["mate_stm"], after["mate_stm"])
                if ep_label in BAD_LABELS
                else None
            )
            best_mv = chess.Move.from_uci(before["best_uci"]) if before["best_uci"] else None
            moves.append(
                {
                    "ply": i + 1,
                    "move_number": before["move_number"],
                    "mover": mover,
                    "san": san,
                    "uci": mv.uci(),
                    "from": chess.square_name(mv.from_square),
                    "to": chess.square_name(mv.to_square),
                    "fen_before": before["fen"],
                    "fen_after": after["fen"],
                    "best_uci": before["best_uci"],
                    "best_san": before["best_san"],
                    "best_from": chess.square_name(best_mv.from_square) if best_mv else None,
                    "best_to": chess.square_name(best_mv.to_square) if best_mv else None,
                    "best_line_san": before["best_line_san"],
                    "second_san": before["second_san"],
                    "ep_second": ep_second,
                    "capture": is_capture,
                    "sacrifice": sac,
                    "sacrifice_piece": sac_piece,
                    "base_label": base_label,
                    "tactic": tactic,
                    "cp_before": before["cp_stm"],
                    "ep_best": ep_best,
                    "ep_after": ep_after,
                    "ep_loss": ep_loss,
                    "ep_label": ep_label,
                    "lichess_best": li_best,
                    "lichess_after": li_after,
                    "lichess_loss": li_loss,
                    "lichess_label": "book" if is_book else label_for_loss(li_loss, is_best),
                    "accuracy": 100.0 if is_book else move_accuracy_pct(100.0 * ep_loss),
                    "phase": phase,
                    "clock_sec": before["clk_white_sec"] if mover == "white" else before["clk_black_sec"],
                }
            )
    finally:
        if book is not None:
            book.close()

    # Lichess's aggregation (volatility-weighted mean + harmonic mean), on our expected-points losses.
    weights = ep_move_weights([p["white_ep_display"] for p in positions])
    for m, w in zip(moves, weights):
        m["weight"] = w

    summary: dict[str, Any] = {}
    for side in ("white", "black"):
        mine = [m for m in moves if m["mover"] == side]
        counts: dict[str, int] = {}
        for m in mine:
            counts[m["ep_label"]] = counts.get(m["ep_label"], 0) + 1
        # Rating-free raw win% drop on every move after the first, as in the fitting data.
        later = [m for m in mine if m["ply"] > 1]
        est = estimate_rating(
            [max(0.0, m["lichess_best"] - m["lichess_after"]) for m in later],
            [abs(m["cp_before"]) for m in later],
            time_class,
            w_elo if side == "white" else b_elo,
        )
        if est is not None and pool != "lichess":
            est = {k: from_lichess_scale(v, pool, time_class) for k, v in est.items()}
        summary[side] = {
            "moves": len(mine),
            "avg_ep_loss": sum(m["ep_loss"] for m in mine) / len(mine) if mine else 0.0,
            "accuracy": combine([m["accuracy"] for m in mine], [m["weight"] for m in mine]) if mine else 100.0,
            "labels": counts,
            "estimated_rating": est,
            "phases": {ph: phase_grade([m for m in mine if m["phase"] == ph]) for ph in ("opening", "middlegame", "endgame")},
        }

    # Key moments: the biggest EP drops that reached at least "mistake" (or a miss), plus brilliant moves.
    key = sorted(
        (m for m in moves if m["ep_label"] in ("mistake", "blunder", "miss")), key=lambda m: m["ep_loss"], reverse=True
    )[:5]
    key += [m for m in moves if m["ep_label"] == "brilliant"][:2]

    def white_display_cp(p: dict[str, Any]) -> dict[str, Any]:
        return {"cp": p["eval_cp_white"], "mate": p["mate_white"]}

    out = {
        "headers": dict(h),
        "white_elo": w_elo_raw,
        "black_elo": b_elo_raw,
        "white_model_elo": w_elo,
        "black_model_elo": b_elo,
        "rating_pool": pool,
        "time_class": time_class,
        "rating_band": band,
        "engine_depth": depth,
        "start_fen": start_fen,
        "positions": [
            {
                "fen": p["fen"],
                "white_ep": p["white_ep_display"],
                "white_lichess": p["lichess_stm"] if p["side_to_move"] == "w" else 1.0 - p["lichess_stm"],
                **white_display_cp(p),
            }
            for p in positions
        ],
        "white_ep_by_ply": [p["white_ep_display"] for p in positions],
        "white_lichess_by_ply": [p["lichess_stm"] if p["side_to_move"] == "w" else 1.0 - p["lichess_stm"] for p in positions],
        "moves": moves,
        "summary": summary,
        "key_moments": sorted(m["ply"] for m in key),
    }
    if keep_rows:
        out["_rows"] = positions
    return out


RETRY_TOLERANCE = 0.02  # an attempt within this EP of the best move counts as finding it ("excellent" band)


def score_attempt(rows: list[dict[str, Any]], move: dict[str, Any], uci: str, model: EPModel, analyse_one) -> dict[str, Any]:
    """
    Judge a move tried in retry mode at the position before `move` (a review move dict). The attempt is
    scored like the played move: the real position's context after the move, with the attempt's eval.
    analyse_one(fen) -> eval fields of a single FEN (EnginePool.analyse_one).
    """
    i = move["ply"] - 1
    board = chess.Board(move["fen_before"])
    mv = chess.Move.from_uci(uci)
    if mv not in board.legal_moves:
        raise ValueError("Illegal move")
    san = board.san(mv)
    board.push(mv)
    terminal = _terminal_score(board)
    row = dict(rows[i + 1])
    row["terminal"] = terminal
    if uci == move["best_uci"]:
        ep = move["ep_best"]
    elif terminal is not None:
        ep = 1.0 - terminal
    else:
        ev = analyse_one(board.fen())
        row.update({k: ev[k] for k in ("eval_cp_white", "mate_white", "eval_cp_stm", "mate_stm", "eval_depth")})
        ep = 1.0 - float(model.predict_rows([row])[0])
    loss = max(0.0, move["ep_best"] - ep)
    is_best = uci == move["best_uci"]
    return {
        "uci": uci,
        "san": san,
        "ep_after": ep,
        "ep_loss": loss,
        "label": label_for_loss(loss, is_best),
        "correct": is_best or loss <= RETRY_TOLERANCE,
        "best_san": move["best_san"],
        "best_line_san": move["best_line_san"],
    }


def print_review(r: dict[str, Any]) -> None:
    h = r["headers"]
    pool_note = f" (model sees {r['white_model_elo']}/{r['black_model_elo']} Lichess)" if r["rating_pool"] != "lichess" else ""
    print(f"{h.get('White', '?')} ({r['white_elo']}) vs {h.get('Black', '?')} ({r['black_elo']}){pool_note}  "
          f"{h.get('Result', '*')}  {r['time_class']}  depth {r['engine_depth']}")
    print(f"{'move':<14}{'EP best':>10}{'EP after':>10}{'EP loss':>9}  {'EP label':<12}{'eval-only':<12}best")
    for m in r["moves"]:
        num = f"{m['move_number']}{'.' if m['mover'] == 'white' else '...'}"
        flag = " *" if m["base_label"] != m["lichess_label"] else ""
        print(
            f"{num + ' ' + m['san']:<14}{m['ep_best']:>10.1%}{m['ep_after']:>10.1%}{m['ep_loss']:>9.1%}  "
            f"{m['ep_label']:<12}{m['lichess_label']:<12}{m['best_san'] or ''}{flag}"
        )
    for side, s in r["summary"].items():
        print(f"{side}: accuracy {s['accuracy']:.1f} | avg EP loss {s['avg_ep_loss']:.1%} | {s['labels']}")
    print("* = EP label differs from the eval-only (Lichess curve) label")


def read_game(pgn_path: Path, index: int = 0) -> chess.pgn.Game | None:
    with open(pgn_path, encoding="utf-8") as f:
        for _ in range(index):
            if chess.pgn.read_game(f) is None:
                return None
        return chess.pgn.read_game(f)


def main(argv: list[str] | None = None) -> int:
    from ep_model.phase_d.engine_pool import EnginePool

    p = argparse.ArgumentParser(description="Phase D: EP-based move review for one PGN")
    p.add_argument("pgn", type=Path)
    p.add_argument("--game-index", type=int, default=0, help="Which game in the file (0-based)")
    p.add_argument("--white-elo", type=int, default=None)
    p.add_argument("--black-elo", type=int, default=None)
    p.add_argument("--rating-pool", choices=["auto", "lichess", "chesscom"], default="auto")
    p.add_argument("--policy", type=Path, default=Path(__file__).resolve().parents[1] / "config" / "engine_policy_parallel.json")
    p.add_argument("--depth", type=int, default=None, help="Override policy depth (model was trained at policy depth)")
    p.add_argument("--workers", type=int, default=4, help="Parallel Stockfish processes")
    p.add_argument("--model-dir", type=Path, default=None)
    p.add_argument("--json", type=Path, default=None, help="Write full review JSON here")
    p.add_argument("--html", type=Path, default=None, help="Write an HTML report here")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")

    game = read_game(args.pgn, args.game_index)
    if game is None:
        LOG.error("No game at index %s in %s", args.game_index, args.pgn)
        return 1

    policy = load_policy(args.policy)
    depth = args.depth or int(policy["depth"])
    model = EPModel(args.model_dir)
    with EnginePool(
        policy.get("stockfish_path", "stockfish"),
        workers=args.workers,
        threads=int(policy.get("threads", 1)),
        hash_mb=int(policy.get("hash_mb", 64)),
    ) as pool:
        result = review_game(
            game,
            model,
            lambda fens, prog: pool.analyse(fens, depth, prog),
            depth,
            args.white_elo,
            args.black_elo,
            args.rating_pool,
        )

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
