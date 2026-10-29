"""
Optional Claude-written explanations for key moments. Off unless ANTHROPIC_API_KEY is set; the app
works the same without it (the template coach is always there).

Claude gets only facts the review already computed (position, move, label, chances, engine line, tactic
hint) and is asked to explain them in plain words, not to analyse the position itself.
"""

from __future__ import annotations

import logging
import os
from typing import Any

LOG = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"
MAX_TOKENS = 4000  # thinking counts against this; the answer itself is 2-3 sentences
TIMEOUT_SEC = 45.0

SYSTEM = (
    "You are a friendly chess coach writing one short note for a game review. Use only the facts given: "
    "the engine's best move and line, the chances (expected score for the player at their rating and clock), "
    "and the tactic hint. Do not invent other variations or evaluations. Write 2-3 plain sentences for a club "
    "player: what went wrong or right, and the idea behind the better move. No headings, no lists, no "
    "centipawns, and use standard algebraic notation for moves."
)


def enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _facts(move: dict[str, Any], headers: dict[str, str], elo: int | None) -> str:
    who = headers.get("White" if move["mover"] == "white" else "Black") or move["mover"].title()
    num = f"{move['move_number']}{'.' if move['mover'] == 'white' else '...'}"
    lines = [
        f"Position before the move (FEN): {move['fen_before']}",
        f"Player: {who} ({move['mover']}{f', rated {elo}' if elo else ''})",
        f"Move played: {num} {move['san']}, labelled {move['ep_label']}",
        f"Chances with the best move: {move['ep_best']:.0%}; after the move played: {move['ep_after']:.0%}",
    ]
    if move.get("best_san") and move["best_san"] != move["san"]:
        lines.append(f"Engine's best move: {move['best_san']}; main line: {' '.join(move.get('best_line_san') or [])}")
    if move.get("second_san"):
        lines.append(f"Engine's second choice: {move['second_san']}")
    if move.get("tactic"):
        lines.append(f"Tactic hint (computed): the move played {move['tactic']}")
    if move.get("sacrifice"):
        lines.append(f"Material given up by the move played: {move['sacrifice']} points ({move.get('sacrifice_piece') or 'material'})")
    return "\n".join(lines)


async def explain_move(move: dict[str, Any], headers: dict[str, str], elo: int | None) -> str:
    """A short explanation, or raises RuntimeError with a user-facing message."""
    import anthropic

    client = anthropic.AsyncAnthropic(timeout=TIMEOUT_SEC, max_retries=2)
    try:
        response = await client.beta.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM,
            output_config={"effort": "low"},
            # Server-side fallback: if a safety classifier declines, the API retries on another model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": _facts(move, headers, elo)}],
        )
    except anthropic.AuthenticationError:
        raise RuntimeError("The Anthropic API key was rejected.") from None
    except anthropic.RateLimitError:
        raise RuntimeError("Too many explanation requests right now; try again in a minute.") from None
    except anthropic.APIStatusError as e:
        LOG.warning("explain failed: %s (request %s)", e.status_code, getattr(e, "request_id", None))
        raise RuntimeError("The explanation service had an error.") from None
    except anthropic.APIConnectionError:
        raise RuntimeError("Couldn't reach the explanation service.") from None
    finally:
        await client.close()

    if response.stop_reason == "refusal":
        raise RuntimeError("No explanation available for this move.")
    text = " ".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        raise RuntimeError("No explanation available for this move.")
    return text
