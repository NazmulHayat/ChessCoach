# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary: club and online players (roughly 800–1800) reviewing one of their own games right after playing it, usually on a laptop. They want to know where the game turned, which of their moves were bad, and what they should have played.

Secondary (not designed for first): recruiters and engineers arriving from the README who try the sample game.

## Product Purpose

elo101 is a free chess game review that runs entirely in the browser. It labels every move Chess.com-style (Brilliant → Blunder), reports accuracy and a game rating, and lets the player retry their mistakes on the board. Success: a player imports a game, understands its turning points in a minute, and retries at least one mistake.

## Positioning

Moves are judged by **expected points at the players' rating and time control** (a model trained on millions of Lichess games), not by raw engine score alone. "+1.5 for two 800s is not +1.5 for two 2200s." The "Chances" view exposes this; the "Engine" view shows raw Stockfish.

## Operating Context

- Import: Chess.com username, Lichess username, or pasted PGN; or a built-in sample (Morphy's Opera Game).
- Analysis: Stockfish WASM runs locally; takes about a minute with a progress readout.
- Summary: result, coach line, eval/chances graph, accuracy per player, game rating, label counts.
- Review: board with eval bar, player bars with clocks and captured pieces, coach bubble per move, graph with label markers, move list, nav controls, Retry, Next mistake, Show best, optional Claude "Explain".
- Keyboard: ← → Home End, Space play, F flip. Settings: board theme, sounds, light/dark.

## Capabilities and Constraints

- React 19 + Vite + react-chessboard; plain CSS in `web/src/index.css` (no Tailwind). Hosted on Vercel.
- No account, nothing uploaded.
- Must stay familiar to Chess.com users: the move-label colours and icons (Brilliant teal !!, Great blue !, Best green ★, … Blunder red ??) and the board-left / panel-right review layout.

## Brand Commitments

- Name: elo101. Knight favicon at `web/public/favicon.svg`.
- Move-label colour/icon conventions above are binding.

## Evidence on Hand

- Benchmark results and figures in `docs/benchmark.md`, `docs/images/`.
- No testimonials, user counts, or press exist; do not invent any.

## Product Principles

1. The board and the player's own mistakes are the point; everything else supports them.
2. Show the rating-aware "chances" idea; it is the reason elo101 exists.
3. Familiar where players rely on habit (labels, layout), distinct everywhere else.
4. Fast and local: no sign-up wall, no waiting UI that hides progress.
