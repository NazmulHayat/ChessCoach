# Resume material

Drafted from [`engineering-log.md`](engineering-log.md). Every number is measured; see the log for how.

## Project summary (2 lines)

**ChessCoach**: an open, measurable rebuild of Chess.com-style Game Review that labels each move by how much it changed the player's real chances at their rating, running entirely in the browser (Stockfish WebAssembly + the ML models client-side, free static hosting).
Python (LightGBM, python-chess, Stockfish) for data and training; TypeScript/React for the app; trained on 12M Lichess positions.

## Bullets (pick 3–4)

- Built an expected-points model (LightGBM) that turns an engine score and both ratings into win chances; on 31,961 held-out positions from 6,403 unseen games it beats Lichess's win% curve by 11.5% in log loss (17% in bullet), with a game-level paired bootstrap confirming each gain.
- Replaced ~60 days of Stockfish compute by harvesting 46.1M already-analysed positions from 84.6M Lichess games in 15 minutes (streaming multi-process parser), and corrected the resulting distribution shift with pretrain-then-fine-tune on 154k clean engine positions.
- Built a fixed benchmark (150 Lichess and 300 Chess.com games with the sites' own verdicts and accuracy, 300 puzzles, 64 known cases, scored per time control, engine results cached so a model scores in ~1 min); it exposed a clock-driven model that labelled a queen blunder "good" in bullet, and the redesigned move-judging model went from 66% to 100% of known cases, 100% of its blunders confirmed by Lichess, and error counts within 2% of Lichess's.
- Moved the whole product client-side, Chessigma-style: Stockfish 18 WebAssembly in one Web Worker per core, LightGBM trees exported to JSON and evaluated in TypeScript, and the review logic ported from Python. 85 parity tests, including 58 full reviews identical in every label and number, keep the two versions in sync. A 61-move game reviews in ~14 s, hosted free on GitHub Pages with no server.
- Validated against independent references and fixed what they found: accuracy within 3 points of Lichess's (chosen on data over a model-based variant), label repeatability 78% → 100% (engine state leaking between positions), 99%+ correct labels on Lichess puzzles, and a Chess.com-style "played like" game rating whose higher side won 94.5% of decisive games.
