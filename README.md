# ChessCoach

**Chess game review that judges moves by your real chances, at your rating, on your clock.**

Stockfish says +1.5 no matter who is playing. ChessCoach asks a different question: *how often does a player at this rating, in this time control, with this much time left, actually score from here?* That number, **expected points (EP)**, drives a Chess.com-style Game Review: every move is labelled by how much it changed the mover's practical chances, not by a fixed centipawn cutoff.

![Game review screen](docs/images/review.png)

Chess.com's current Game Review also uses an expected-points model built from rating and engine eval ([their docs](https://support.chess.com/en/articles/8572705-how-are-moves-classified-what-is-a-blunder-or-brilliant-move)). ChessCoach is an **open, measurable rebuild of that idea, extended with time pressure**: it also conditions on time control and clock, is trained on the public Lichess database, and publishes how well it is calibrated against simpler baselines.

## Results

Held-out test: **31,961 positions from 6,403 games** that no model saw, labelled with our own Stockfish (depth 17). Split by game. Lower log loss is better.

| Model | Training data | Log loss | Brier |
|---|---|---|---|
| **EP model, fine-tuned** | 12M harvested Lichess positions, then 154k Stockfish positions | **0.575** | **0.189** |
| EP model, Stockfish data only | 181k Stockfish positions | 0.579 | 0.190 |
| EP model, harvested data only | 12M harvested Lichess positions | 0.581 | 0.192 |
| Eval-only LightGBM (same model, no context) | 181k | 0.627 | 0.210 |
| Lichess win% formula | none | 0.649 | 0.215 |
| Constant | none | 0.693 | 0.240 |

- **11.5% lower log loss than the Lichess win% curve**, 8.3% lower than an eval-only model: the value of rating, clock and time-control context.
- **Bullet**: 0.586 vs 0.705 for the Lichess curve (−17%), where time pressure matters most.
- **Pretrain + fine-tune is significantly better** than training on the clean data alone: −0.0043 log loss, 95% CI −0.0065 to −0.0021 (paired bootstrap over games).
- **Calibrated**: in every 10-point bin, the actual score is within 1.5 points of the prediction.

Where the 12M positions came from: about 1 in 9 games in the Lichess dump was already analysed by Lichess's servers and carries an engine eval on every move. Harvesting those gave **46.1M labelled positions from 84.6M games in 15 minutes**, with no Stockfish time. Details in [`docs/methodology.md`](docs/methodology.md).

## The Game Review app

| Import | Summary |
|---|---|
| ![Import screen](docs/images/import.png) | ![Summary screen](docs/images/summary.png) |

- **Import** from a Chess.com or Lichess username (recent games, no login), or paste a PGN.
- **Live analysis**: Stockfish runs on a pool of parallel engines (a 60-move game at depth 17 in about 8 s); progress streams to the page.
- **Summary**: accuracy for both players, an estimated **game rating** (what rating you played like, fitted on 397k Lichess player-games: blitz error 292 points vs 362 for a blind guess), label counts, **opening / middlegame / endgame grades**, key moments, advantage graph.
- **Review**: board with move badges, last-move highlight, best-move arrows, move animation, captured pieces and material lead in the player bars; eval bar that switches between **Chances** (EP) and raw **Engine** score; a coach that explains each move and points out where an eval-only review would disagree; clickable graph; move list; flip button; keyboard (← → Home End, Space to play, F to flip).
- **Settings**: four board themes and move sounds (synthesised with Web Audio, no audio files), saved per browser. Works on phones (single-column layout, tap-to-move in retry mode).
- **Labels** use Chess.com's published expected-points bands: best (engine move), excellent < 2%, good < 5%, inaccuracy < 10%, mistake < 20%, blunder ≥ 20%, plus book moves from a polyglot opening book.
- **Great / Miss / Brilliant**: our own documented rules on the engine's top two lines. Great = the only good move; Miss = gives back most of the opponent's mistake; Brilliant = a sound sacrifice (static-exchange check) that wasn't needed to stay winning. Thresholds scale with rating. Rules in [`docs/methodology.md`](docs/methodology.md#great-miss-and-brilliant).
- **Retry**: on a mistake, miss or blunder, play a better move on the board (drag or tap). The server scores your attempt with the same EP model; within 2% of the best move counts. **Next mistake** steps through your own errors.

## Quick start

Requirements: Python 3.11+, Node 18+, and [Stockfish](https://stockfishchess.org/) on your `PATH`.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd web && npm install && npm run build && cd ..

python -m ep_model.phase_d.server          # → http://127.0.0.1:8000
```

The trained model ships in `ep_model/models_finetuned/`, so the app works right after cloning; retrain with the steps below. Lighter engine pass: `--depth 12 --workers 2`. Frontend development with hot reload: run the server, then `cd web && npm run dev`.

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
rows_with_eval_*.parquet  (clean set: fine-tuning + held-out test)

Same dump ── harvest: read Lichess's own [%eval] annotations (9.2M analysed games, 15 min)
   ▼
rows_lichess_*.parquet  (46M positions, pretraining)

   │  Phase C  LightGBM pretrain on harvested data → fine-tune on clean data → evaluate vs baselines
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
python -m ep_model.harvest.lichess_evals     # Lichess server evals → ep_model/processed_lichess/
python -m ep_model.phase_c.train -v          # clean model + held-out test split
python -m ep_model.phase_c.train --processed-dir ep_model/processed_lichess --pattern "rows_lichess_part*.parquet" \
    --max-rows 12000000 --num-leaves 127 --output-dir ep_model/models_lichess
python -m ep_model.phase_c.finetune          # → ep_model/models_finetuned (used by the app)
python -m ep_model.phase_c.evaluate --extra-model ep_lichess=ep_model/models_lichess \
    --extra-model ep_finetuned=ep_model/models_finetuned     # → ep_model/models/ep_eval_report.md
# or all of it: ep_model/scripts/run_big_training.sh
```

Pipeline details: [`ep_model/README.md`](ep_model/README.md). Design decisions and caveats: [`docs/methodology.md`](docs/methodology.md).

## Project layout

| Path | What |
|---|---|
| `ep_model/phase_a/` | Stream the dump, sample positions, extract ratings / clocks / result |
| `ep_model/phase_b/` | Stockfish evals with FEN cache, checkpoints and parallel workers |
| `ep_model/harvest/` | Extract positions with Lichess server evals straight from the dump |
| `ep_model/phase_c/` | Feature prep, LightGBM training, fine-tuning, baseline evaluation with bootstrap CIs |
| `ep_model/phase_d/` | `EPModel` predictor, move review, engine pool, FastAPI server |
| `ep_model/scripts/` | `safe_run` (long Phase B runs with health checks, retries), full pipeline script |
| `web/` | React + Vite + TypeScript frontend |
| `tests/` | pytest suite (row generation, features, evaluation helpers, review logic) |
| `archive/` | Earlier rule-based move classifier, kept for reference |

## Roadmap

- Pretrain on all 46M harvested positions (memory permitting) and finish the Stockfish test set.

## Credits

Game data: [Lichess open database](https://database.lichess.org/) (CC0). Engine: [Stockfish](https://stockfishchess.org/) (GPLv3, run as a separate program). Board: [react-chessboard](https://github.com/Clariity/react-chessboard) (MIT) and [chess.js](https://github.com/jhlywa/chess.js) (BSD). Not affiliated with Chess.com or Lichess.
