"""
Phase A row generation: per sampled half-move, fields before engine augmentation.
See ep_model/TRAINING_PLAN.md.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Any

import chess
import chess.pgn

CLK_RE = re.compile(r"\[%clk\s+([^\]]+)\]")

# Rating bucket by average rating (stratification label)
RATING_BUCKETS = [0, 1000, 1200, 1400, 1600, 1800, 2000, 3000]


def extract_game_id(site: str) -> str:
    """Stable id from Lichess Site header (URL last segment)."""
    if not site or not site.strip():
        return "unknown"
    s = site.rstrip("/").strip()
    part = s.split("/")[-1]
    return part if part else s


def parse_time_control(tc: str | None) -> tuple[int | None, int | None]:
    """
    Parse TimeControl header: '300+0', '180+2', or single number in seconds.
    Returns (initial_time_sec, increment_sec).
    """
    if not tc or tc == "-" or tc == "?":
        return None, None
    tc = tc.strip()
    if "+" in tc:
        a, b = tc.split("+", 1)
        try:
            return int(a.strip()), int(b.strip())
        except ValueError:
            return None, None
    try:
        return int(tc), 0
    except ValueError:
        return None, None


def classify_time_class(initial_sec: int | None) -> str:
    """Rough Lichess-like class from initial clock (seconds)."""
    if initial_sec is None:
        return "unknown"
    if initial_sec < 180:
        return "bullet"
    if initial_sec < 480:
        return "blitz"
    if initial_sec < 1500:
        return "rapid"
    return "classical"


def rating_band_from_average(avg_elo: float) -> str:
    """Bucket label for average of WhiteElo and BlackElo."""
    x = int(avg_elo)
    for lo, hi in zip(RATING_BUCKETS[:-1], RATING_BUCKETS[1:]):
        if lo <= x < hi:
            return f"{lo}-{hi}"
    return f"{RATING_BUCKETS[-2]}+"


def parse_result_header(result: str | None) -> tuple[float | None, float | None]:
    """
    Returns (result_white, result_black) each in {0, 0.5, 1} or (None, None) if unfinished/invalid.
    """
    if not result:
        return None, None
    r = result.strip()
    if r == "1-0":
        return 1.0, 0.0
    if r == "0-1":
        return 0.0, 1.0
    if r == "1/2-1/2":
        return 0.5, 0.5
    if r == "*" or r == "":
        return None, None
    return None, None


def result_stm(result_white: float, white_to_move: bool) -> float:
    """Game outcome from side-to-move perspective (0 / 0.5 / 1)."""
    if white_to_move:
        return result_white
    return 1.0 - result_white


def parse_clock_comment(comment: str | None) -> float | None:
    """Parse [%clk H:MM:SS] or [%clk M:SS] to seconds."""
    if not comment:
        return None
    m = CLK_RE.search(comment)
    if not m:
        return None
    return parse_clock_token(m.group(1).strip())


def parse_clock_token(token: str) -> float | None:
    """Clock string like '0:05:00' or '5:00' to total seconds."""
    parts = token.split(":")
    try:
        if len(parts) == 3:
            h, mn, s = parts
            return int(h) * 3600 + int(mn) * 60 + float(s)
        if len(parts) == 2:
            mn, s = parts
            return int(mn) * 60 + float(s)
    except (ValueError, TypeError):
        return None
    return None


def parse_clock_header(h: str | None) -> float | None:
    """WhiteClock / BlackClock header values."""
    if not h:
        return None
    return parse_clock_token(h.strip())


def game_phase_from_half_moves(half_moves_played: int) -> str:
    """Heuristic opening / middlegame / endgame from half-move count before current move."""
    if half_moves_played < 20:
        return "opening"
    if half_moves_played < 60:
        return "middlegame"
    return "endgame"


def _elo_int(headers: dict[str, str], key: str) -> int | None:
    raw = headers.get(key)
    if not raw or raw == "?":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


@dataclass
class GameMeta:
    game_id: str
    white_elo: int | None
    black_elo: int | None
    result_white: float | None
    result_black: float | None
    time_class: str
    initial_time_sec: int | None
    increment_sec: int | None
    opening_eco: str | None
    rating_band: str
    stratum_key: str


def build_game_meta(game: chess.pgn.Game) -> GameMeta | None:
    """Headers + derived stratification; returns None if game should be skipped."""
    h = game.headers
    site = h.get("Site", "")
    game_id = extract_game_id(site)
    white_elo = _elo_int(h, "WhiteElo")
    black_elo = _elo_int(h, "BlackElo")
    if white_elo is None or black_elo is None:
        return None
    rw, rb = parse_result_header(h.get("Result"))
    if rw is None:
        return None
    init, inc = parse_time_control(h.get("TimeControl"))
    tc = classify_time_class(init)
    avg = (white_elo + black_elo) / 2.0
    band = rating_band_from_average(avg)
    stratum_key = f"{band}_{tc}"
    eco = h.get("ECO") or None
    return GameMeta(
        game_id=game_id,
        white_elo=white_elo,
        black_elo=black_elo,
        result_white=rw,
        result_black=rb,
        time_class=tc,
        initial_time_sec=init,
        increment_sec=inc,
        opening_eco=eco,
        rating_band=band,
        stratum_key=stratum_key,
    )


def collect_mainline_moves(game: chess.pgn.Game) -> list[chess.pgn.ChildNode]:
    """Ordered mainline child nodes (each has .move and .comment)."""
    out: list[chess.pgn.ChildNode] = []
    node: chess.pgn.GameNode = game
    while node.variations:
        ch = node.variation(0)
        out.append(ch)
        node = ch
    return out


def extract_rows_for_game(
    game: chess.pgn.Game,
    meta: GameMeta,
    rng: random.Random,
    k_plies: int,
) -> list[dict[str, Any]]:
    """Sample up to k distinct half-moves from the main line and return row dicts."""
    moves = collect_mainline_moves(game)
    if not moves:
        return []

    n = len(moves)
    k = min(k_plies, n)
    indices = set(rng.sample(range(n), k=k))

    board = game.board()
    clk_w = parse_clock_header(game.headers.get("WhiteClock"))
    clk_b = parse_clock_header(game.headers.get("BlackClock"))

    rows: list[dict[str, Any]] = []
    for i, next_node in enumerate(moves):
        move = next_node.move

        fen = board.fen()
        white_to_move = board.turn == chess.WHITE
        side = "w" if white_to_move else "b"
        elo_to_move = meta.white_elo if white_to_move else meta.black_elo
        elo_opponent = meta.black_elo if white_to_move else meta.white_elo
        assert elo_to_move is not None and elo_opponent is not None
        stm = result_stm(meta.result_white, white_to_move)

        half_played = len(board.move_stack)
        phase = game_phase_from_half_moves(half_played)

        row = {
            "game_id": meta.game_id,
            "ply": i + 1,
            "move_number": board.fullmove_number,
            "side_to_move": side,
            "fen": fen,
            "played_move_uci": move.uci(),
            "white_elo": meta.white_elo,
            "black_elo": meta.black_elo,
            "elo_to_move": elo_to_move,
            "elo_opponent": elo_opponent,
            "elo_diff": elo_to_move - elo_opponent,
            "time_class": meta.time_class,
            "initial_time_sec": meta.initial_time_sec,
            "increment_sec": meta.increment_sec,
            "clk_white_sec": clk_w,
            "clk_black_sec": clk_b,
            "phase": phase,
            "opening_eco": meta.opening_eco,
            "result_white": meta.result_white,
            "result_stm": stm,
            "rating_band": meta.rating_band,
            "stratum_key": meta.stratum_key,
        }
        if i in indices:
            rows.append(row)

        clk_after = parse_clock_comment(next_node.comment)
        board.push(move)
        if clk_after is not None:
            if board.turn == chess.BLACK:
                clk_w = clk_after
            else:
                clk_b = clk_after

    return rows


def extract_rows_for_game_fixed(
    game: chess.pgn.Game,
    rng: random.Random,
    k_plies: int,
) -> list[dict[str, Any]]:
    """Convenience: build meta and rows; returns [] if meta invalid."""
    meta = build_game_meta(game)
    if meta is None:
        return []
    return extract_rows_for_game(game, meta, rng, k_plies)
