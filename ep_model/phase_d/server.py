"""
Local web app for EP game review: JSON API + the built React frontend (web/dist).

Usage (repo root):
  python -m ep_model.phase_d.server                  # http://127.0.0.1:8000
  python -m ep_model.phase_d.server --depth 12 --workers 2

Environment (all optional; the Docker image sets them): CHESSCOACH_DEPTH, CHESSCOACH_WORKERS,
CHESSCOACH_MAX_CONCURRENT (reviews analysed at once, others get 503), CHESSCOACH_REVIEWS_PER_HOUR
(per client IP, 0 = unlimited), CHESSCOACH_MAX_PLIES (longest game accepted), PORT, HOST.

API:
  POST /api/review                 {pgn, white_elo?, black_elo?, rating_pool?, depth?} → server-sent events
                                   (event: progress {done, total} …, then event: result {review} or event: error)
  POST /api/retry                  {review_id, ply, uci} → is this move as good as the engine's? (retry mode)
  POST /api/explain                {review_id, ply} → Claude-written note on a move (only with ANTHROPIC_API_KEY)
  GET  /api/games/chesscom/{user}  recent Chess.com games (public API)
  GET  /api/games/lichess/{user}   recent Lichess games (public API)
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import logging
import os
import threading
import time
import uuid
from collections import OrderedDict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import chess.pgn
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ep_model.phase_a.rowgen import classify_time_class, parse_time_control
from ep_model.phase_b.augment_evals import load_policy
from ep_model.phase_d import explain
from ep_model.phase_d.engine_pool import EnginePool
from ep_model.phase_d.predictor import EPModel
from ep_model.phase_d.review import review_game, score_attempt

LOG = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[2]
WEB_DIST = REPO / "web" / "dist"
DEFAULT_POLICY = REPO / "ep_model" / "config" / "engine_policy_parallel.json"
DEFAULT_ELO = 1500
GAMES_LIMIT = 25
# Chess.com asks API clients to identify themselves.
HTTP_HEADERS = {"User-Agent": "ChessCoach/0.1 (local EP game review app)"}

CONFIG: dict[str, Any] = {
    "depth": int(os.environ.get("CHESSCOACH_DEPTH", "0")) or None,
    "workers": int(os.environ.get("CHESSCOACH_WORKERS", "4")),
    "policy": Path(os.environ.get("CHESSCOACH_POLICY", str(DEFAULT_POLICY))),
    "max_concurrent": int(os.environ.get("CHESSCOACH_MAX_CONCURRENT", "4")),
    "reviews_per_hour": int(os.environ.get("CHESSCOACH_REVIEWS_PER_HOUR", "0")),
    "max_plies": int(os.environ.get("CHESSCOACH_MAX_PLIES", "600")),
}


class RateLimiter:
    """Sliding one-hour window of events per key (client IP). limit <= 0 means unlimited."""

    def __init__(self, limit: int, window_sec: float = 3600.0):
        self.limit, self.window = limit, window_sec
        self._events: dict[str, deque] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        if self.limit <= 0:
            return True
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._events.setdefault(key, deque())
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


def client_ip(request: Request) -> str:
    """Real client address behind Fly.io / Render / other proxies."""
    for header in ("fly-client-ip", "true-client-ip"):
        if request.headers.get(header):
            return request.headers[header]
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
STATE: dict[str, Any] = {}
# Recent reviews' model rows, so retry mode can score a tried move in the same context. In memory only:
# after a restart the client falls back to checking the engine's top move.
REVIEWS: OrderedDict[str, dict[str, Any]] = OrderedDict()
REVIEWS_MAX = 200
_reviews_lock = threading.Lock()


def _remember_review(result: dict[str, Any]) -> str:
    rid = uuid.uuid4().hex
    with _reviews_lock:
        REVIEWS[rid] = {
            "rows": result.pop("_rows"),
            "moves": result["moves"],
            "depth": result["engine_depth"],
            "headers": result["headers"],
            "elos": {"white": result["white_elo"], "black": result["black_elo"]},
            "explanations": {},
        }
        while len(REVIEWS) > REVIEWS_MAX:
            REVIEWS.popitem(last=False)
    return rid


@asynccontextmanager
async def lifespan(app: FastAPI):
    policy = load_policy(CONFIG["policy"])
    STATE["depth"] = CONFIG["depth"] or int(policy["depth"])
    STATE["model"] = EPModel()
    STATE["pool"] = EnginePool(
        policy.get("stockfish_path", "stockfish"),
        workers=CONFIG["workers"],
        threads=int(policy.get("threads", 1)),
        hash_mb=int(policy.get("hash_mb", 64)),
    )
    STATE["review_slots"] = asyncio.Semaphore(max(1, CONFIG["max_concurrent"]))
    STATE["limiter"] = RateLimiter(CONFIG["reviews_per_hour"])
    LOG.info(
        "Ready: depth %s, %s engines, %s concurrent reviews, %s reviews/hour/IP",
        STATE["depth"], CONFIG["workers"], CONFIG["max_concurrent"], CONFIG["reviews_per_hour"] or "unlimited",
    )
    try:
        yield
    finally:
        STATE["pool"].close()


app = FastAPI(title="ChessCoach", lifespan=lifespan)


class ReviewRequest(BaseModel):
    pgn: str = Field(min_length=1, max_length=200_000)
    white_elo: int | None = Field(default=None, ge=100, le=3500)
    black_elo: int | None = Field(default=None, ge=100, le=3500)
    rating_pool: str = Field(default="auto", pattern="^(auto|lichess|chesscom)$")
    depth: int | None = Field(default=None, ge=6, le=22)


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _parse_game(pgn: str) -> chess.pgn.Game:
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None or game.errors or not list(game.mainline_moves()):
        raise ValueError("Couldn't read a game from that PGN.")
    return game


def _elo_or_none(headers: chess.pgn.Headers, key: str) -> int | None:
    try:
        return int(headers.get(key, ""))
    except ValueError:
        return None


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "depth": STATE.get("depth"), "workers": CONFIG["workers"], "explain": explain.enabled()}


@app.post("/api/review")
async def review(req: ReviewRequest, request: Request) -> StreamingResponse:
    try:
        game = _parse_game(req.pgn)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    plies = sum(1 for _ in game.mainline_moves())
    if plies > CONFIG["max_plies"]:
        raise HTTPException(status_code=413, detail=f"Game too long ({plies} half-moves; the limit is {CONFIG['max_plies']}).")
    slots: asyncio.Semaphore = STATE["review_slots"]
    if slots.locked():
        raise HTTPException(status_code=503, detail="The server is busy analysing other games. Try again in a minute.")
    if not STATE["limiter"].allow(client_ip(request)):
        raise HTTPException(status_code=429, detail="Review limit reached for this hour. Try again later.")

    h = game.headers
    white_elo = req.white_elo or _elo_or_none(h, "WhiteElo") or DEFAULT_ELO
    black_elo = req.black_elo or _elo_or_none(h, "BlackElo") or DEFAULT_ELO
    # Never deeper than the server is configured for (the model was trained at depth 17).
    depth = min(req.depth or STATE["depth"], STATE["depth"])
    loop = asyncio.get_running_loop()
    events: asyncio.Queue = asyncio.Queue()

    def progress(done: int, total: int) -> None:
        loop.call_soon_threadsafe(events.put_nowait, ("progress", {"done": done, "total": total}))

    def work() -> None:
        try:
            result = review_game(
                game,
                STATE["model"],
                lambda fens, prog: STATE["pool"].analyse(fens, depth, prog),
                depth,
                white_elo,
                black_elo,
                req.rating_pool,
                progress=progress,
                keep_rows=True,
            )
            result["review_id"] = _remember_review(result)
            loop.call_soon_threadsafe(events.put_nowait, ("result", result))
        except Exception as e:  # surfaced to the client as an error event
            LOG.exception("review failed")
            loop.call_soon_threadsafe(events.put_nowait, ("error", {"detail": str(e)}))

    await slots.acquire()

    async def stream():
        try:
            task = loop.run_in_executor(None, work)
            while True:
                event, data = await events.get()
                yield _sse(event, data)
                if event in ("result", "error"):
                    break
            await task
        finally:
            slots.release()

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


class RetryRequest(BaseModel):
    review_id: str = Field(min_length=1, max_length=64)
    ply: int = Field(ge=1, le=2000)
    uci: str = Field(pattern="^[a-h][1-8][a-h][1-8][qrbn]?$")


@app.post("/api/retry")
async def retry(req: RetryRequest) -> dict[str, Any]:
    with _reviews_lock:
        saved = REVIEWS.get(req.review_id)
    if saved is None:
        raise HTTPException(status_code=410, detail="This review is no longer on the server; analyse the game again.")
    if req.ply > len(saved["moves"]):
        raise HTTPException(status_code=400, detail="No such move.")
    move = saved["moves"][req.ply - 1]
    depth = saved["depth"]

    def work() -> dict[str, Any]:
        return score_attempt(saved["rows"], move, req.uci, STATE["model"], lambda fen: STATE["pool"].analyse_one(fen, depth))

    try:
        return await asyncio.get_running_loop().run_in_executor(None, work)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


EXPLAIN_PER_REVIEW = 30


class ExplainRequest(BaseModel):
    review_id: str = Field(min_length=1, max_length=64)
    ply: int = Field(ge=1, le=2000)


@app.post("/api/explain")
async def explain_move(req: ExplainRequest) -> dict[str, Any]:
    if not explain.enabled():
        raise HTTPException(status_code=404, detail="Explanations are off (no ANTHROPIC_API_KEY on the server).")
    with _reviews_lock:
        saved = REVIEWS.get(req.review_id)
    if saved is None:
        raise HTTPException(status_code=410, detail="This review is no longer on the server; analyse the game again.")
    if req.ply > len(saved["moves"]):
        raise HTTPException(status_code=400, detail="No such move.")
    cache = saved["explanations"]
    if req.ply in cache:
        return {"ply": req.ply, "text": cache[req.ply]}
    if len(cache) >= EXPLAIN_PER_REVIEW:
        raise HTTPException(status_code=429, detail="Explanation limit reached for this game.")
    move = saved["moves"][req.ply - 1]
    try:
        text = await explain.explain_move(move, saved["headers"], saved["elos"][move["mover"]])
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from None
    cache[req.ply] = text
    return {"ply": req.ply, "text": text}


def _result_for(white: str, black: str, user: str, result: str) -> str:
    """'win' / 'loss' / 'draw' from `user`'s point of view."""
    if result == "1/2-1/2":
        return "draw"
    white_won = result == "1-0"
    is_white = white.lower() == user.lower()
    return "win" if white_won == is_white else "loss"


@app.get("/api/games/chesscom/{user}")
async def chesscom_games(user: str) -> list[dict[str, Any]]:
    user = user.strip().lower()
    async with httpx.AsyncClient(headers=HTTP_HEADERS, timeout=15) as client:
        r = await client.get(f"https://api.chess.com/pub/player/{user}/games/archives")
        if r.status_code == 404:
            raise HTTPException(status_code=404, detail=f"No Chess.com player '{user}'.")
        r.raise_for_status()
        archives = r.json().get("archives", [])
        games: list[dict[str, Any]] = []
        for url in reversed(archives[-3:]):
            ar = await client.get(url)
            ar.raise_for_status()
            games.extend(reversed(ar.json().get("games", [])))
            if len(games) >= GAMES_LIMIT:
                break
    out = []
    for g in games:
        if g.get("rules") != "chess" or not g.get("pgn"):
            continue
        w, b = g["white"], g["black"]
        pgn_game = chess.pgn.read_game(io.StringIO(g["pgn"]))
        result = pgn_game.headers.get("Result", "*") if pgn_game else "*"
        init, inc = parse_time_control(g.get("time_control"))
        out.append(
            {
                "id": g.get("uuid") or g.get("url"),
                "site": "chesscom",
                "url": g.get("url"),
                "white": w.get("username"),
                "black": b.get("username"),
                "white_elo": w.get("rating"),
                "black_elo": b.get("rating"),
                "result": result,
                "user_result": _result_for(w.get("username", ""), b.get("username", ""), user, result),
                "time_control": g.get("time_control"),
                "time_class": g.get("time_class") or classify_time_class(init),
                "end_time": datetime.fromtimestamp(g.get("end_time", 0), tz=timezone.utc).isoformat(),
                "pgn": g["pgn"],
            }
        )
        if len(out) >= GAMES_LIMIT:
            break
    return out


@app.get("/api/games/lichess/{user}")
async def lichess_games(user: str) -> list[dict[str, Any]]:
    user = user.strip()
    params = {"max": GAMES_LIMIT, "pgnInJson": "true", "clocks": "true", "opening": "true"}
    async with httpx.AsyncClient(headers={**HTTP_HEADERS, "Accept": "application/x-ndjson"}, timeout=20) as client:
        r = await client.get(f"https://lichess.org/api/games/user/{user}", params=params)
        if r.status_code == 404:
            raise HTTPException(status_code=404, detail=f"No Lichess player '{user}'.")
        r.raise_for_status()
    out = []
    for line in r.text.splitlines():
        if not line.strip():
            continue
        g = json.loads(line)
        if g.get("variant", "standard") != "standard" or not g.get("pgn"):
            continue
        players = g.get("players", {})
        w, b = players.get("white", {}), players.get("black", {})
        wn = (w.get("user") or {}).get("name", "Anonymous")
        bn = (b.get("user") or {}).get("name", "Anonymous")
        winner = g.get("winner")
        result = "1-0" if winner == "white" else "0-1" if winner == "black" else "1/2-1/2"
        clock = g.get("clock") or {}
        out.append(
            {
                "id": g.get("id"),
                "site": "lichess",
                "url": f"https://lichess.org/{g.get('id')}",
                "white": wn,
                "black": bn,
                "white_elo": w.get("rating"),
                "black_elo": b.get("rating"),
                "result": result,
                "user_result": _result_for(wn, bn, user, result),
                "time_control": f"{clock.get('initial', 0)}+{clock.get('increment', 0)}" if clock else "-",
                "time_class": g.get("speed"),
                "end_time": datetime.fromtimestamp(g.get("lastMoveAt", g.get("createdAt", 0)) / 1000, tz=timezone.utc).isoformat(),
                "pgn": g["pgn"],
            }
        )
    return out


if WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")


def main(argv: list[str] | None = None) -> int:
    import uvicorn

    p = argparse.ArgumentParser(description="ChessCoach EP review web app")
    p.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    p.add_argument("--depth", type=int, default=None, help="Stockfish depth (default: policy depth, 17)")
    p.add_argument("--workers", type=int, default=CONFIG["workers"], help="Parallel Stockfish processes")
    p.add_argument("--policy", type=Path, default=CONFIG["policy"])
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    CONFIG.update(depth=args.depth or CONFIG["depth"], workers=args.workers, policy=args.policy)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
