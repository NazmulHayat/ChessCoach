# ChessCoach

Chess game review that judges moves by **expected points (EP)**: the score a player at *this* rating, in *this* time control, with *this* much clock, actually goes on to get from a position. Stockfish says +1.5 regardless of who is playing; EP says what +1.5 is worth to a 1200 in bullet vs a 2200 in rapid.

The EP model is LightGBM trained on Lichess games: Stockfish eval + ratings + clocks + time control + phase/opening → expected score for the side to move.

## Active layout

| Path | Role |
|------|------|
| `ep_model/` | EP pipeline: Phase A (sample positions) → B (Stockfish) → C (LightGBM + evaluation) → D (PGN review). See `ep_model/README.md`. |
| `engine/` | Shared UCI Stockfish wrapper (used by EP Phase B and archived move-review). |
| `tests/` | Active tests (e.g. `test_ep_phase_a_rowgen.py`). |

## Quick start (EP)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m ep_model.phase_a.generate_rows --max-games 2000
python -m ep_model.phase_b.augment_evals --max-rows 3000 -v
python -m ep_model.phase_c.train -v
python -m ep_model.phase_c.evaluate -v                 # EP vs eval-only baselines → models/ep_eval_report.md
python -m ep_model.phase_d.review game.pgn --html review.html
# Long Phase B on a laptop: batched runner + background engine policy (see ep_model/README.md)
# python -m ep_model.scripts.safe_run
```

Place Lichess `*.pgn.zst` under `ep_model/raw/` (see `ep_model/README.md`).

## Game Review web app

Chess.com-style review UI on top of the EP model: import a game (Chess.com or Lichess username, or paste a PGN), watch it get analysed, then step through it with an eval bar (your chances or raw engine), move badges, best-move arrows, a coach explaining every move, a clickable advantage graph and a summary with accuracy and label counts.

```bash
cd web && npm install && npm run build && cd ..   # once, or after frontend changes
python -m ep_model.phase_d.server                 # http://127.0.0.1:8000
# lighter engine pass while something else is using the CPU:
python -m ep_model.phase_d.server --depth 12 --workers 2
```

Frontend dev with hot reload: run the server, then `cd web && npm run dev` (Vite proxies `/api` to port 8000).

Labels follow Chess.com's published expected-points bands (best / excellent < 2% / good < 5% / inaccuracy < 10% / mistake < 20% / blunder), plus book moves from a polyglot opening book. Chess.com ratings are mapped to the Lichess scale the model was trained on (approximate). Pieces: cburnett set (open licence).

## Archived code

Older move-classification / docs / one-off scripts are under `archive/` (see `archive/README.md`). They stay in git for reference; Cursor ignores that folder via `.cursorignore`.
