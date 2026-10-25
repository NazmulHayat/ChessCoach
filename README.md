# ChessCoach

**Chess game review that judges moves by your real chances, at your rating, on your clock.**

Stockfish says +1.5 no matter who is playing. ChessCoach asks a different question: *how often does a player at this rating, in this time control, with this much time left, actually score from here?* That number, **expected points (EP)**, drives a Chess.com-style Game Review: every move is labelled by how much it changed the mover's practical chances, not by a fixed centipawn cutoff.

![Game review screen](docs/images/review.png)

Chess.com's current Game Review also uses an expected-points model built from rating and engine eval ([their docs](https://support.chess.com/en/articles/8572705-how-are-moves-classified-what-is-a-blunder-or-brilliant-move)). ChessCoach is an **open, measurable rebuild of that idea, extended with time pressure**: it also conditions on time control and clock, is trained on the public Lichess database, and publishes how well it is calibrated against simpler baselines.

## Results

Held-out evaluation, split by game so no game appears in both train and test. Lower log loss is better.

| Model | Log loss | Brier |
|---|---|---|
| **EP model** (eval + ratings + clocks + time control) | **0.574** | **0.188** |
| Eval-only LightGBM (same model class, no context) | 0.627 | 0.210 |
| Eval-only logistic fit | 0.627 | 0.210 |
| Lichess win% formula | 0.650 | 0.215 |
| Constant | 0.693 | 0.241 |

- **11.7% lower log loss than the Lichess win% curve**, 8.4% lower than an eval-only model trained on the same data. That second gap is the value of rating, clock and time-control context.
- **Biggest gain in bullet** (0.580 vs 0.708 for the Lichess curve), where time pressure matters most.
- **Well calibrated**: in every 10-point bin, the actual score is within 2.5 points of the prediction (e.g. predicted 75%, actual 76%).

> Interim numbers: 138k training / 24k held-out positions (4,900 games). A full run on ~558k positions is in progress; this table will be updated when it finishes.

## The Game Review app

| Import | Summary |
|---|---|
| ![Import screen](docs/images/import.png) | ![Summary screen](docs/images/summary.png) |

- **Import** from a Chess.com or Lichess username (recent games, no login), or paste a PGN.
- **Live analysis**: Stockfish runs on a pool of parallel engines; progress streams to the page.
- **Summary**: accuracy for both players, label counts, key moments, advantage graph.
- **Review**: board with move badges, last-move highlight and best-move arrows; eval bar that switches between **Chances** (EP) and raw **Engine** score; a coach that explains each move and points out where an eval-only review would disagree; clickable graph; move list; keyboard (← → Home End, Space to play, F to flip).
- **Labels** use Chess.com's published expected-points bands: best (engine move), excellent < 2%, good < 5%, inaccuracy < 10%, mistake < 20%, blunder ≥ 20%, plus book moves from a polyglot opening book.

## Quick start

Requirements: Python 3.11+, Node 18+, and [Stockfish](https://stockfishchess.org/) on your `PATH`.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd web && npm install && npm run build && cd ..

python -m ep_model.phase_d.server          # → http://127.0.0.1:8000
```

The server needs a trained model in `ep_model/models/` (see below). Lighter engine pass: `--depth 12 --workers 2`. Frontend development with hot reload: run the server, then `cd web && npm run dev`.

Command-line review without the UI:

```bash
python -m ep_model.phase_d.review game.pgn --html review.html
```

## How it works

```
Lichess dump (.pgn.zst)
   │  Phase A  stream games, sample ~5 positions per game, keep ratings, clocks, result
   ▼
rows_no_eval_*.parquet
   │  Phase B  Stockfish depth 17 on every position (parallel engines, FEN cache, resumable)
   ▼
rows_with_eval_*.parquet
   │  Phase C  LightGBM, cross-entropy on game outcome, split by game, evaluate vs baselines
   ▼
ep_lgbm.txt
   │  Phase D  review any game: engine eval per position → EP per move → labels → web app
   ▼
FastAPI + React Game Review
```

Train your own model:

```bash
# put a Lichess monthly dump (database.lichess.org) at ep_model/raw/*.pgn.zst
python -m ep_model.phase_a.generate_rows --max-games 100000 --resume
python -m ep_model.scripts.safe_run --policy ep_model/config/engine_policy_parallel.json --workers 8
python -m ep_model.phase_c.train --sharded-load -v
python -m ep_model.phase_c.evaluate -v      # → ep_model/models/ep_eval_report.md
# or all of it: ep_model/scripts/run_big_training.sh
```

Pipeline details: [`ep_model/README.md`](ep_model/README.md). Design decisions and caveats: [`docs/methodology.md`](docs/methodology.md).

## Project layout

| Path | What |
|---|---|
| `ep_model/phase_a/` | Stream the dump, sample positions, extract ratings / clocks / result |
| `ep_model/phase_b/` | Stockfish evals with FEN cache, checkpoints and parallel workers |
| `ep_model/phase_c/` | Feature prep, LightGBM training, baseline evaluation |
| `ep_model/phase_d/` | `EPModel` predictor, move review, engine pool, FastAPI server |
| `ep_model/scripts/` | `safe_run` (long Phase B runs with health checks, retries), full pipeline script |
| `web/` | React + Vite + TypeScript frontend |
| `tests/` | pytest suite (row generation, features, evaluation helpers, review logic) |
| `archive/` | Earlier rule-based move classifier, kept for reference |

## Roadmap

- Final model on the full ~558k-position run; refresh results above.
- Great / Miss / Brilliant labels (needs the engine's second-best move).
- "Retry move": find the better move yourself on the board.
- Move sounds, estimated game rating, opening / middlegame / endgame grades.

## Credits

Game data: [Lichess open database](https://database.lichess.org/) (CC0). Engine: [Stockfish](https://stockfishchess.org/) (GPLv3, run as a separate program). Board: [react-chessboard](https://github.com/Clariity/react-chessboard) (MIT) and [chess.js](https://github.com/jhlywa/chess.js) (BSD). Not affiliated with Chess.com or Lichess.
