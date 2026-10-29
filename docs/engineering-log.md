# Engineering log

What was built, the numbers behind it, and the problems solved along the way. Newest last.

## Timeline

| Date | Milestone |
|---|---|
| 2026-03 | Rule-based Chess.com-style move classifier (PGN → Stockfish → labels), golden tests. Archived. |
| 2026-03 | Pivot to an expected-points (EP) model. Phase A (sample positions from a 26 GB Lichess dump), Phase B (Stockfish depth 17, FEN cache, resumable checkpoints, `safe_run` with disk/swap/heat guards), Phase C (LightGBM). Pilot on 3k rows. |
| 2026-10-25 | Baseline evaluation, training fixes, Phase D review, parallel engines, web app, eval harvesting, pretrain + fine-tune (below). |
| 2026-10-25 | Great / Miss / Brilliant labels (multipv=2, SEE-based sacrifice check), Retry mode with server-side scoring of tried moves. |
| 2026-10-25 | Game rating estimate, opening / middlegame / endgame grades. |
| 2026-10-25 | UI polish: move / capture / check sounds (Web Audio), captured material, flip button, settings (board theme, sounds), skeletons, server-down banner, error boundary, mobile check at 390 px. |
| 2026-10-25 | Coach: tactic hints (missed / allowed mate, hanging pieces, missed material) and engine main line; optional Claude explanations behind ANTHROPIC_API_KEY. |
| 2026-10-25 | Pretrain on 25M harvested rows (2× data): not significantly better than the shipped 12M model, so not shipped. |
| 2026-10-25 | Phase B continuous queue (measured +2%), Dockerfile (Stockfish 18 compiled in), Fly.io / Render configs, request limits. Label frequencies on 200 real games. |
| 2026-10-25 | Independent validation (Lichess puzzles, Lichess's own move verdicts, repeatability); fixes: Lichess accuracy formula, Chess.com-style performance rating, deterministic engine jobs. |
| 2026-10-25 | Runs fully in the browser (Stockfish WASM workers, models as JSON, review ported to TypeScript with parity tests); static hosting on GitHub Pages. Accuracy switched to Lichess's formula on our evals, chosen on the benchmark. |
| 2026-10-25 | User-reported bullet game exposed clock-driven labels. Built a fixed benchmark (Lichess, Chess.com, puzzles, known cases; per time class); split the chances model from a board-only move-judging model chosen on it. "Played like" game rating in the UI. |
| 2026-10-29 | PyTorch MLP comparison (ties the shipped model; not shipped). Repository cleanup: descriptive package names, CI, license. |
| 2026-10-30 | Renamed to **elo101**, hosted on Vercel. Game rating now follows accuracy; stricter Brilliant. |

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
| Training run | 12M rows, 734 trees, 252 s on a laptop; 25M rows, 1,353 trees, 978 s, 4.9 GB peak RAM |
| PyTorch MLP vs LightGBM (same 181k clean rows) | 0.5745 / 0.5760 / 0.5766 over 3 seeds vs 0.5788; vs shipped fine-tuned model 0.5746: no significant difference (best −0.0001, 95% CI −0.0026 to +0.0023); 42k parameters, ~10 s per run; not shipped |
| 25M vs 12M pretraining (both fine-tuned) | 0.5743 vs 0.5746 log loss; paired difference −0.0002, 95% CI −0.0011 to +0.0007: no significant gain, 12M model kept |
| App latency | full 62-move game at depth 17: 8.1 s with 4 engines and one line per position; 23.8 s after switching to two lines (multipv=2, needed for Great / Brilliant); 0.07 s on a repeat (FEN cache) |
| Game rating (performance) | monotone in accuracy, both players anchored on the game average; 200k analysed games, 0 order contradictions in 40k held out; blitz: 68.2% vs 32.1% mean score above / below own rating (was 63.5% vs 37.9%) |
| Brilliant | 132 → 11 on 450 benchmark games (0.42% → 0.03% of moves) after requiring an accepted, kept sacrifice |
| Puzzle validation | 300 Lichess puzzles: solution move best/great/brilliant 99.3%; the puzzle's blunder flagged 100% when the player wasn't already lost (93.0% overall) |
| Agreement with Lichess's verdicts | 100 games, 6,016 moves: 94.6% of our blunders are also Lichess errors; 1.1% false alarms on moves Lichess leaves unmarked |
| Accuracy formula | matches Lichess's displayed accuracy within 0.32 points on average (94% within rounding), 762 player scores |
| Repeatability | same label on re-review 78.2% → 100% (engine cleared before each position), +5% review time (22.3 → 23.6 s per game) |
| Special label frequencies | 200 random Lichess games, 13,971 moves, depth 17: Great 2.8%, Miss 1.7%, Brilliant 0.31%; stable across rating bands (Great 2.6–2.9%, Brilliant 0.25–0.53%) |
| Phase B dispatch | continuous queue vs 256-row chunks: 8.91 → 9.09 positions/s (+2%, within run-to-run noise), 768 positions, 8 engines |
| Docker image | 1.16 GB (Python 3.12 slim + Stockfish 18 built from source + model); full 13-move review in 11.6 s with 2 engines |
| multipv=2 cost | 0.414 → 0.605 s/position at depth 17 (+46%); top-line eval drift median 7.5 cp, p90 27 cp (120 positions) |
| Benchmark | 150 Lichess + 300 Chess.com games, 300 puzzles, 64 known cases; Stockfish cached per position, a model scores in ~1 min |
| Move-judging model vs clock model (benchmark) | Lichess blunders called mistake+ 64.7% → 79.4%; our blunders confirmed by Lichess 95.3% → 100%; error count vs Lichess 0.81 → 1.02; known cases 65.6% → 100% |
| In-browser review | 61-move bullet game in ~14 s (Chrome, 10-core laptop); Stockfish lite 7 MB, models 9.6 MB JSON; lite vs native evals: median 16 cp, best move same 77.5% |
| Browser parity | 85 vitest tests: 400 model rows within 1e-9, helper checks on 240 positions / 5,000+ moves, 58 full reviews identical to Python |
| Accuracy choice (benchmark) | Lichess formula on our evals vs on EP loss: gap to Lichess 3.1 vs 5.6, to Chess.com 8.1 vs 9.1, winner-picking 0.960 vs 0.957 |
| Tests | 67 pytest tests + 84 Vitest tests (row generation, features, evaluation, review logic, special labels, retry scoring, rating estimate, tactics, explanations, harvest parsing) |

## Problems solved

1. **Wrong training objective.** Regression with MAE early stopping pulls predictions toward 0 / 0.5 / 1 for a win/draw/loss target. Switched to cross-entropy: calibrated probabilities, log loss 0.591 → 0.574.
2. **Clockless games broke the model.** Lichess rows almost always have clocks, so "missing clock" only appeared on move 1 and the model treated it as a strong signal; every move in a Chess.com PGN looked like a blunder. Fixed with side-to-move-relative clock features plus clock dropout (15% of training games blanked).
3. **Side-to-move bias created fake move losses.** Comparing EP before vs after a move mixed two different "who is on move" contexts. Redesigned move loss as a counterfactual: score the played move and the engine's best move on identical opponent-to-move rows, so the bias cancels.
4. **Engine underused the CPU.** One 2-thread Stockfish on a 10-core machine. Added a worker pool (one single-threaded engine per thread, ordered output, shared FEN cache) and automatic retry when macOS kills an engine under memory pressure.
5. **Chunked dispatch stalls: measured, smaller than estimated.** Phase B waited for the slowest position in each 256-row chunk before starting the next. Replaced with a continuous queue (sliding window, in-order output, shared FEN dedupe). Measured on 768 positions, 8 engines, depth 17, fresh caches, alternating order: 8.91 → 9.09 positions/s (+2%), smaller than the run-to-run spread (81–91 s). The earlier "~20%" was an estimate; with 32 positions per engine per chunk, the idle tail was only about one position per chunk. Kept for simpler code and no worst case, not for speed.
6. **Biggest speedup was not computing at all.** ~11% of games in the dump already carry Lichess server analysis (`[%eval]` on every move). A streaming, multi-process parser (no board replay, backpressured so memory stays flat) extracted 46.1M labelled positions in 14.8 minutes, versus an estimated ~60 days of Stockfish at depth 17 even with the 8-engine pool (46.1M ÷ 8.9 positions/s). Stockfish-labelled games are excluded so they remain a clean, unbiased test set.
7. **Training at tens of millions of rows on a 24 GB laptop.** Column pruning, categorical strings, in-place feature building and random-shard row caps.
8. **Rating pools differ.** The model learned Lichess ratings; Chess.com ratings are mapped onto that scale per time class.
9. **More data alone didn't win: distribution shift.** Trained only on the harvested positions, the model was slightly overconfident on the clean test set (predicted 64%, actual 61%) and not significantly better than the clean-only model (+0.0024, CI −0.0018 to +0.0065). Diagnosed: different search budget and self-selected games. Fixed with pretrain-then-fine-tune (continue the boosted trees on clean data, early-stopped on clean games outside the test set): significantly better than both.
10. **Proving the gain is real.** Added a paired bootstrap over whole games (positions in a game are correlated) so every model comparison reports a 95% CI, not just a point estimate.
11. **"Sacrifice" needs a counterfactual too.** A naive "piece left en prise" check calls every trapped piece a sacrifice. The SEE-based check compares the move against the safest legal alternative and only counts material the player chose to give up.
12. **Drag-and-drop died after the first wrong retry.** Two react-chessboard quirks: dragging is wired up only when the board mounts (toggling `arePiecesDraggable` later leaves pieces undraggable), and its drop handler can be a closure from an earlier render. Fixed by keeping the board draggable for the whole retry session (remount per session) and reading the current move handler through a ref. Found with a scripted Playwright test that drags pieces.
13. **One game's accuracy barely predicts rating.** Least squares on accuracy and error rates: blunder-rate-style features gave blitz MAE 341 vs 364 for guessing the median (r = 0.34). Adding accuracy in balanced positions and mean |eval| (separating "accurate because the game was easy" from "accurate in a fight") with a small LightGBM: MAE 292 (r = 0.59). Opponent rating left out on purpose, since matchmaking would leak it.
14. **More pretraining data stopped helping.** Doubling the harvested pretraining set (12M → 25M rows, 1,353 trees, 978 s, 4.9 GB peak) gave 0.5743 vs 0.5746 on the clean test set after the same fine-tune, a −0.0002 difference with a 95% CI of −0.0011 to +0.0007. Not significant, so the smaller model stays (12.8 MB vs 22.5 MB). The limit is now the clean data and the features, not pretraining volume. Decided by the pre-registered rule: ship only on a significant paired-bootstrap gain.
15. **Accuracy was inflated.** A plain average of per-move accuracy showed 99.7 for a game with mistakes. Switched to Lichess's published method (volatility-weighted mean + harmonic mean) and checked it against the accuracy Lichess shows on 381 real games from its API: within 0.32 points on average. Matching it exposed an undocumented detail: Lichess floors each move at 1 in the harmonic mean (with ~0, one game was off by 15 points).
16. **"Game rating" regressed everyone to the average.** The first model minimised error against the player's rating, which is the least-wrong guess but useless as "you played like X" (a 99.7-accuracy game by a ~1900 player came out ~1500). Inverting it ("which rating plays like this?") swung far too wide (blitz MAE 430 vs 362 for guessing the median). Final version follows Chess.com's description: start from your rating and move it by how much better or worse you played than players at your rating, scaled by how much one game can tell (Elo's 200-point single-game spread). Validated by outcome: 63.5% vs 37.9% mean score for players rated above vs below their rating in that game.
17. **Same game, different labels.** A re-review kept the same label on only 78.2% of moves: each Stockfish process carried hash and history from earlier positions, so results depended on thread scheduling. Clearing the engine before every position made it 100%, at about 5% more time (22.3 → 23.6 s per game, 4 engines). A first measurement suggested 2× slower; it had run alongside other jobs, and a clean A/B on the same 8 games showed the real cost.

18. **The model judged moves by the clock.** A user's 1+0 bullet game showed 0 blunders and 94% accuracy; Lichess found 2 blunders and 81%. Giving away a queen for a rook cost 2.5% "chances" and was labelled good. Not a data bug (evals line up: mate-in-1 positions score 96%); the clock-aware model was right that 1+0 games are decided by the clock (1.5–4 pawns up with ~24 s each scores 51% in Lichess data). Fix: keep that model for the chances bar, judge moves with a board-only model (no clock features, monotone in eval, rapid / classical games). Same game: accuracy 96.5 / 94.0 → 90.2 / 81.4 vs Lichess's 91 / 81.
19. **No standard to catch it.** Every earlier check was a one-off script averaged over all time controls, so a bullet-only failure stayed hidden. Built a fixed benchmark with targets, per time class: frozen Lichess games (recent, outside the training month), Chess.com games with Chess.com's accuracy, puzzles, and known cases including traps replayed with either side nearly flagging. Engine results cached per position, so comparing models takes a minute instead of an hour. The old model failed 22 of 64 known cases; the shipped one fails none.
20. **"Great" for taking a free piece.** The Great rule excluded recaptures but not capturing a hanging piece (Qxg5 after Bg5?? was "Great"). Now any capture of the most material available by static exchange (≥ 2 points) is just Best. Found by the known-case set.

21. **Free hosting meant moving the server into the browser.** A server costs money and stalls under load; Chessigma-style, everything now runs client-side: Stockfish 18 lite WebAssembly in one worker per core, the LightGBM models exported to JSON and evaluated in TypeScript with LightGBM's exact split / missing-value rules, and the review rules ported module by module. Kept honest by parity tests against Python on identical engine evals (58 full reviews identical). The full 113 MB engine exceeds GitHub Pages' 100 MB file limit, so the 7 MB lite net is used; its evals differ by a median 16 cp.
22. **Two draws that weren't on the board.** The port's first parity run differed on 2 of ~3,000 moves: python-chess counts a position as drawn when a threefold repetition can be *claimed by the next move*, which chess.js doesn't. Ported python-chess's rule (positions since the last irreversible move, transposition keys with legal en passant only).
23. **Static exchange was 50× too slow in the browser.** chess.js generates SAN for every legal move; sacrifice checks call it thousands of times per game. Using its internal move generator (pinned to chess.js 1.4.0) took the helper test from over 5 minutes to 6 s.
24. **Accuracy formula chosen on data.** With Chess.com's own accuracy now in the benchmark, Lichess's formula on our engine's evals beat the same formula on EP loss against both Lichess and Chess.com and picked winners as well, so the app switched.

25. **"Played like" exploded to 3190.** In bullet a 1450 and a 2650 produce nearly the same typical game, so mapping one game's quality score back to a rating amplified noise ~5× and two ~1570 players both came out at the top of the table. Compared five formulas on 889 benchmark player-games; shipped plays-like capped at your rating ± 400 (FIDE's single-game performance bound), applied on the displayed rating scale.
26. **Tested a per-move "which rating errs like this?" game rating before building it (experiment, not shipped).** 60k analysed Lichess rapid games (120k player-games, 4.0M moves) not used by the shipped model, split by player. The proposed least-squares fit (expected loss by rating and context, pick the closest rating) did worst: single-game MAE 538 vs 364 for the shipped plays-like (median-guess baseline 324). Replacing it with a likelihood (probability of each loss size given rating, eval, clock, ply) brought it to 367, with 80% intervals that hold the player's rating 81.6% of the time on held-out players (median width 1,100 points: one rapid game says little). Alone it did not beat the shipped game-level features (corr 0.533 vs 0.560 on the same 12k fitting games); combined with them it helped a little: corr 0.586, plays-like MAE 354, 5-game average MAE 186 vs 192. Not yet bootstrap-tested; position difficulty (gap to the second-best move) needs our own engine runs, as the dump has no second line.

## Product

- FastAPI server: streamed analysis (server-sent events), parallel engine pool with FEN cache, Chess.com and Lichess public-API import.
- React + Vite + TypeScript UI modelled on Chess.com's Game Review layout: board with move badges and best-move arrows, eval bar (EP or engine), coach text, clickable advantage graph, move list, keyboard controls, summary with accuracy, label counts and key moments.
- Labels follow Chess.com's published expected-points bands; book moves from a polyglot opening book; Great / Miss / Brilliant from documented rules on the engine's top two lines.
- Coach: rule-based tactic hints from python-chess static exchange and mate scores; optional Claude-written notes grounded only in computed facts, off without an API key.
- Polish: synthesised move sounds (no audio assets), captured material and lead per player, four board themes, loading skeletons, error states (server unreachable, failed analysis with one-click retry, React error boundary), mobile layout.
- Retry mode: replay a mistake on the board, judged by the same EP model; "Next mistake" steps through your own errors.

## Findings worth telling

- Chess.com's current Game Review also uses an expected-points model, built from rating and engine eval. This project's model adds time control and clocks, and is evaluated in the open against simpler baselines.
- Hyperparameter tuning moved log loss by < 0.001; data volume is the lever. That observation is what motivated the harvesting approach.


27. **Game rating contradicted the accuracy on screen.** In Morphy's Opera Game, 98.8 vs 85.1 accuracy came out 1300 vs 1200 for two 1500-rated players: the LightGBM quality score treated a lopsided position as an easy game. Replaced it with one monotone accuracy → rating curve per time class (fitted on 200k analysed Lichess games), with both players anchored on the game's average rating, so the order follows accuracy by construction: 0 contradictions in 40,000 held-out games. A hard ±400 cap then tied 54% of bullet games; a smooth limit scaled by each time class's spread, plus continuing the curve past its ends, brought ties down to 11–17% (the rounding to 100). Blitz players who came out above their rating scored 68.2% vs 32.1% below (was 63.5% vs 37.9%); the higher game rating won 95.6% of decisive benchmark games (was 94.5%).
28. **Brilliant was too easy.** On 450 benchmark games it fired 132 times (0.42% of moves), mostly quick tactics (Nxe4 and a fork wins the piece back) and pieces the opponent simply shouldn't take. Brilliant now needs the engine's own move and a sacrifice the engine's main line accepts and keeps for three plies (or mates): 11 left (0.03%). The Opera Game keeps 16. Qb8+!! and drops 13. Rxd7, as in the classical annotations.

## UI polish pass (2026-10-25)

- **Foundation:** design tokens (surfaces, text, status colors, spacing, radii, shadows, motion), consistent button and focus states, Inter with a system fallback, reduced-motion support.
- **Import:** welcome screen, a bundled 13-ply sample game, the last five reviewed games in browser storage, progress with move count and ETA.
- **Review:** board sized around the player bars, taller advantage graph with tooltip and keyboard selection, compact coach, summary with accuracy columns.
- **Sound:** synthesised wood-tap and chime sounds for nine events (no audio files shipped), silent when stepping backward, saved volume.
- **Help:** label and metric popovers, `?` for keyboard shortcuts, a dismissible first-review tour.
- **Phone and themes:** width-constrained phone layout, swipe navigation, System / Light / Dark themes that follow the OS live.

**Flaky test run.** The 58 parity reviews are synchronous and CPU-heavy, so Vitest's worker never yielded to the event loop and the runner reported `Timeout calling "onTaskUpdate"` after all 85 tests had passed, failing the run. Yielding once between tests (`afterEach` with a zero-delay timer) fixed it without touching any assertion.

## Repository cleanup (2026-10-29)

- Pipeline packages renamed by what they do: `phase_a` → `sampling`, `phase_b` → `labeling`, `phase_c` → `training`, `phase_d` → `review` (the stages are still called A–D in this log).
- CI on every push: pytest (with Stockfish), ESLint, Vitest and the production build.
- Legacy engine wrapper moved into `archive/`, duplicate requirement files merged, project metadata and tool config in `pyproject.toml`.

## Visual redesign: "Club Night" (2026-10-30)

- **Process:** design critique, a product brief (`PRODUCT.md`), five competing directions sketched as HTML and picked by the user, then a code build reviewed by an independent design reviewer over desktop (dark/light) and phone screenshots. Three review rounds; every material finding resolved except one deferred item (below). System recorded in `DESIGN.md`.
- **Look:** the board sits on a green club "mat" with printed a–h / 1–8 coordinates and the eval bar in its margin; panels are buff scoresheet paper. Green marks where you are (current move, active tab), brass marks what you can do (primary actions). Bricolage Grotesque + Figtree. Chess.com move-label colours and board-left / panel-right layout kept on purpose. New default board theme "Club"; light/dark and the other board themes stay in Settings.
- **Bugs the review surfaced:** checkmate positions (engine `mate = 0`) were scored for the losing side (eval bar "M0" full black after White mated); now the side to move is the loser and the bar reads 1-0 / 0-1. Play and Next shared one icon. The graph's current-move line used an undefined colour and never drew.
- **Open:** captured pieces in the player bars are still Unicode glyphs; an SVG piece set needs a licence decision.

### Summary panel rework (2026-10-30)
- Sections (Accuracy, Moves, Phases, Key moments) now share one left-aligned heading style.
- Move counts sit in pills sized by count and tinted with the label colour (white grows from the left, black from the right); zeros show "–"; a stronger rule separates good moves from errors; "Show all / Hide empty" is a quiet text link in the heading and only appears when some labels are empty.
- Phase grades show the phase accuracy next to the grade icon instead of hiding it behind a tap.
- Key moments align with the panel gutter, show who played the move, and draw a small chances track: kept chances in ink, the part the move gave away in its label colour.
