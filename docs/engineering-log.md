# Engineering log

What was built, the numbers behind it, and the problems solved along the way. Newest last.

## Timeline

| Date | Milestone |
|---|---|
| 2026-03 | Rule-based Chess.com-style move classifier (PGN → Stockfish → labels), golden tests. Archived. |
| 2026-03 | Pivot to an expected-points (EP) model. Phase A (sample positions from a 26 GB Lichess dump), Phase B (Stockfish depth 17, FEN cache, resumable checkpoints, `safe_run` with disk/swap/heat guards), Phase C (LightGBM). Pilot on 3k rows. |
| 2026-10-25 | Baseline evaluation, training fixes, Phase D review, parallel engines, web app, eval harvesting, pretrain + fine-tune (below). |

| 2026-10-25 | Game rating estimate, opening / middlegame / endgame grades. |
| 2026-10-25 | Great / Miss / Brilliant labels (multipv=2, SEE-based sacrifice check), Retry mode with server-side scoring of tried moves. |

## Key numbers

| What | Value |
|---|---|
| Source data | Lichess Feb 2026 dump: 26 GB compressed, ~85M rated games |
| Stockfish-labelled set (Phase A/B) | 558k sampled positions from 112k games; 213k evaluated at depth 17 (clean held-out test set) |
| Harvested set | 9.23M of 84.6M games already analysed by Lichess's servers; 46.1M labelled positions extracted with zero engine time (776 MB Parquet) |
| Phase B throughput | ~1.9 → ~8.9 positions/s (~4.6×) with 8 parallel single-threaded engines (was one 2-thread engine at 0.52 s/position) |
| Harvest throughput | 84.6M games scanned in 14.8 min (~95k games/s) on a 10-core laptop |
| Final model | pretrained on 12M harvested positions, fine-tuned on 154k Stockfish positions |
| Held-out test | 31,961 positions / 6,403 unseen games, Stockfish depth 17 |
| Final vs Lichess win% curve | log loss 0.575 vs 0.649 (−11.5%); vs eval-only LightGBM 0.627 (−8.3%) |
| Pretrain + fine-tune vs clean-only | −0.0043 log loss, 95% CI −0.0065 to −0.0021 (paired bootstrap over games) |
| Bullet games | 0.586 vs 0.705 for the Lichess curve (−17%) |
| Calibration | every 10-point bin within 1.5 points |
| Training run | 12M rows, 734 trees, 252 s on a laptop |
| App latency | full 62-move game reviewed at depth 17 in 8.1 s (4 engines) |
| Game rating estimate | LightGBM on 397k player-games (200k Lichess-analysed games), held out by game: blitz MAE 292 vs 362 median baseline (−19%), rapid 252 vs 322 (−22%), classical 188 vs 238, bullet 332 vs 376; data extraction + fit in about 3 minutes |
| multipv=2 cost | 0.414 → 0.605 s/position at depth 17 (+46%); top-line eval drift median 7.5 cp, p90 27 cp (120 positions) |
| Tests | 37 pytest tests (row generation, features, evaluation, review logic, special labels, retry scoring, harvest parsing) |

## Problems solved

1. **Wrong training objective.** Regression with MAE early stopping pulls predictions toward 0 / 0.5 / 1 for a win/draw/loss target. Switched to cross-entropy: calibrated probabilities, log loss 0.591 → 0.574.
2. **Clockless games broke the model.** Lichess rows almost always have clocks, so "missing clock" only appeared on move 1 and the model treated it as a strong signal; every move in a Chess.com PGN looked like a blunder. Fixed with side-to-move-relative clock features plus clock dropout (15% of training games blanked).
3. **Side-to-move bias created fake move losses.** Comparing EP before vs after a move mixed two different "who is on move" contexts. Redesigned move loss as a counterfactual: score the played move and the engine's best move on identical opponent-to-move rows, so the bias cancels.
4. **Engine underused the CPU.** One 2-thread Stockfish on a 10-core machine. Added a worker pool (one single-threaded engine per thread, ordered output, shared FEN cache) and automatic retry when macOS kills an engine under memory pressure.
5. **Chunked dispatch stalls** (identified): workers idle waiting for the slowest position in each chunk; a continuous queue would add ~20%.
6. **Biggest speedup was not computing at all.** ~11% of games in the dump already carry Lichess server analysis (`[%eval]` on every move). A streaming, multi-process parser (no board replay, backpressured so memory stays flat) extracted 46.1M labelled positions in 14.8 minutes, versus an estimated ~60 days of Stockfish at depth 17 even with the 8-engine pool (46.1M ÷ 8.9 positions/s). Stockfish-labelled games are excluded so they remain a clean, unbiased test set.
7. **Training at tens of millions of rows on a 24 GB laptop.** Column pruning, categorical strings, in-place feature building and random-shard row caps.
9. **More data alone didn't win: distribution shift.** Trained only on the harvested positions, the model was slightly overconfident on the clean test set (predicted 64%, actual 61%) and not significantly better than the clean-only model (+0.0024, CI −0.0018 to +0.0065). Diagnosed: different search budget and self-selected games. Fixed with pretrain-then-fine-tune (continue the boosted trees on clean data, early-stopped on clean games outside the test set): significantly better than both.
10. **Proving the gain is real.** Added a paired bootstrap over whole games (positions in a game are correlated) so every model comparison reports a 95% CI, not just a point estimate.
8. **Rating pools differ.** The model learned Lichess ratings; Chess.com ratings are mapped onto that scale per time class.
11. **"Sacrifice" needs a counterfactual too.** A naive "piece left en prise" check calls every trapped piece a sacrifice. The SEE-based check compares the move against the safest legal alternative and only counts material the player chose to give up.
13. **One game's accuracy barely predicts rating.** Least squares on accuracy and error rates: blunder-rate-style features gave blitz MAE 341 vs 364 for guessing the median (r = 0.34). Adding accuracy in balanced positions and mean |eval| (separating "accurate because the game was easy" from "accurate in a fight") with a small LightGBM: MAE 292 (r = 0.59). Opponent rating left out on purpose, since matchmaking would leak it.
12. **Drag-and-drop died after the first wrong retry.** Two react-chessboard quirks: dragging is wired up only when the board mounts (toggling `arePiecesDraggable` later leaves pieces undraggable), and its drop handler can be a closure from an earlier render. Fixed by keeping the board draggable for the whole retry session (remount per session) and reading the current move handler through a ref. Found with a scripted Playwright test that drags pieces.

## Product

- FastAPI server: streamed analysis (server-sent events), parallel engine pool with FEN cache, Chess.com and Lichess public-API import.
- React + Vite + TypeScript UI modelled on Chess.com's Game Review layout: board with move badges and best-move arrows, eval bar (EP or engine), coach text, clickable advantage graph, move list, keyboard controls, summary with accuracy, label counts and key moments.
- Labels follow Chess.com's published expected-points bands; book moves from a polyglot opening book; Great / Miss / Brilliant from documented rules on the engine's top two lines.
- Retry mode: replay a mistake on the board, judged by the same EP model; "Next mistake" steps through your own errors.

## Findings worth telling

- Chess.com's current Game Review also uses an expected-points model, built from rating and engine eval. This project's model adds time control and clocks, and is evaluated in the open against simpler baselines.
- Hyperparameter tuning moved log loss by < 0.001; data volume is the lever. That observation is what motivated the harvesting approach.
