# Resume material

Drafted from [`engineering-log.md`](engineering-log.md). Every number is measured; see the log for how.

## Project summary (2 lines)

**ChessCoach**: an open, measurable rebuild of Chess.com-style Game Review that labels each move by how much it changed the player's real chances at their rating, time control and clock, instead of fixed engine-score cutoffs.
Python (LightGBM, python-chess, Stockfish, FastAPI) + React/TypeScript; trained on 12M Lichess positions, deployed as one Docker image.

## Bullets (pick 3–4)

- Built an expected-points model (LightGBM, cross-entropy) conditioned on rating, time control and clocks; on 31,961 held-out positions from 6,403 unseen games it reaches 0.575 log loss vs 0.649 for Lichess's win% curve (−11.5%, −17% in bullet), with a game-level paired bootstrap confirming the pretrain + fine-tune gain (−0.0043, 95% CI −0.0065 to −0.0021).
- Replaced an estimated ~60 days of Stockfish compute by harvesting 46.1M already-analysed positions from 84.6M Lichess games in 14.8 minutes (~95k games/s, streaming multi-process parser), then fixed the resulting distribution shift (overconfident 64% vs 61% actual) by pretraining on 12M harvested rows and fine-tuning on 154k clean depth-17 Stockfish positions.
- Shipped a full-stack Game Review app (FastAPI with server-sent events, React/TypeScript, pool of parallel Stockfish engines) with Brilliant / Great / Miss rules built on static exchange evaluation, and validated the labels against independent references: on 300 Lichess puzzles the winning move is rated best/great/brilliant 99.3% of the time, and 94.6% of its blunders are also errors in Lichess's deeper analysis (100 games, 6,016 moves).
- Found and fixed three issues through that testing: inflated accuracy (re-implemented Lichess's formula, matching its displayed accuracy within 0.32 points over 762 player scores), a game rating that regressed every player to the average (rebuilt as a performance rating that tracks outcomes: 63.5% vs 37.9% mean score above vs below one's rating), and engine nondeterminism (label repeatability 78% → 100%).
- Sped up engine labelling 4.6× (1.9 → 8.9 positions/s) with a single-threaded engine pool and shared FEN cache; packaged the app as a Docker image with Stockfish 18 compiled in, per-IP rate limits and concurrency caps; 52 pytest tests plus scripted Playwright browser QA.
