# Methodology

How the expected-points (EP) model is built and used, the decisions behind it, and its known limits.

## What EP means

For a position with side *S* to move, EP is the expected game score for *S* (win = 1, draw = 0.5, loss = 0) given:

- the Stockfish evaluation (fixed depth 17, mate scores mapped to a pseudo-centipawn scale),
- both players' ratings and their difference,
- time control (initial time, increment, bullet / blitz / rapid / classical),
- both clocks (side-to-move relative: my time, opponent's time, fraction of my initial time left),
- move number and a coarse game phase, and the opening (ECO code).

## Data

Source: one Lichess monthly rated-games dump (February 2026, 84.6M games), streamed without decompressing to disk. About 5 random positions per game, so no single game dominates. Label: the final game result from the side to move's point of view (every sampled position of a game shares that result).

Two sets, with no game in both:

| Set | How the eval was made | Size | Used for |
|---|---|---|---|
| **Clean** (Phase A/B) | Our Stockfish, fixed depth 17, on a random sample of games | 213k positions, 42.7k games | fine-tuning and the held-out test |
| **Harvested** | Lichess's own server analysis (`[%eval]` in the PGN, Stockfish via fishnet, roughly 1.5–2M nodes per position) on games players chose to analyse | 46.1M positions, 9.2M games | pretraining |

The harvested set is huge and free, but it differs from the clean set in two ways: its evals come from a different search budget, and analysed games are self-selected. Trained on it alone, the model was slightly overconfident on the clean test set (e.g. predicting 64% where players scored 61%) and not significantly better than the clean-only model. Pretraining on it and then fine-tuning on the clean set (continuing the same boosted trees for 85 more rounds at a lower learning rate, early-stopped on clean games outside the test set) fixed that and beat both, significantly.

**More pretraining data.** Pretraining on 25M harvested rows instead of 12M (then the same fine-tune) reached 0.5743 vs 0.5746 log loss on the test set: a paired difference of −0.0002 (95% CI −0.0011 to +0.0007). Not significant, so the 12M model stays.

## Training choices

| Decision | Why |
|---|---|
| **Split by game**, never by row | Positions from one game are strongly correlated (same players, same result). A row split leaks the answer and inflates scores. |
| **Cross-entropy objective** | The target is a probability-like expected score. L2/MAE pull predictions toward 0 / 0.5 / 1; cross-entropy gives calibrated probabilities. |
| **Side-to-move-relative clocks** | "My clock vs theirs" generalises across colours better than white/black clocks. |
| **Clock dropout (15% of games)** | Lichess rows almost always have clocks; many PGNs (e.g. some Chess.com exports) don't. Without this, "no clock" was only seen on move 1 and the model behaved badly on clockless games. |
| **LightGBM with categorical features** | Fast, strong on tabular data, handles ECO codes and time classes natively. A hyperparameter sweep moved log loss by < 0.001, so defaults are kept; more data is the lever. |

## Evaluation

`python -m ep_model.phase_c.evaluate` scores the held-out games with the EP model and four baselines:

1. **Constant**: mean training outcome.
2. **Lichess win% formula**: `1 / (1 + exp(-0.00368208 · cp))`, cp clipped to ±1000.
3. **Eval-only logistic** fit on the same training games.
4. **Eval-only LightGBM**: same model class, only the engine score.

Every model is also compared to the clean-only EP model with a **paired bootstrap over games** (1,000 resamples of whole games, since positions in a game are correlated), giving a 95% CI on the log-loss difference.

Baseline 4 is the important comparison: the gap between it and the EP model is the value of the context features, with model capacity held equal. The report also breaks results down by rating band and time class and includes a calibration table.

## From EP to move labels

For each move the review computes:

- **EP if best**: the mover's EP had they played Stockfish's best move.
- **EP after**: the mover's EP after the move actually played.
- **EP loss** = max(0, EP if best − EP after).

Both numbers are scored on an *opponent-to-move* row with identical context (same ply, clocks, ratings), differing only in the engine eval. The model has a small side-to-move bias; comparing like with like cancels it. An earlier version compared "before the move" with "after the move" directly, and that bias showed up as a fake ~20% loss on every move.

Labels then use Chess.com's published bands: best (engine move), excellent < 0.02, good < 0.05, inaccuracy < 0.10, mistake < 0.20, blunder ≥ 0.20. Book moves come from a polyglot opening book. The same bands applied to the Lichess win% curve give the "eval-only" label the coach compares against.

### Great, Miss and Brilliant

Chess.com describes these only in words, so these are our own rules, written in expected points. The engine runs with `multipv=2`, so the second-best move and its eval are known; its EP is scored with the same counterfactual row as the best move. Code: `ep_model/phase_d/special.py`, tests: `tests/test_phase_d_special.py`.

| Label | Rule (mover's EP) |
|---|---|
| **Great** | The engine's best move, and the second-best move is at least *G* worse (an only move), or the best move keeps a better outcome band (losing < 30%, winning > 70%) than the second-best with a gap ≥ 5%. Not for forced moves (one legal move), immediate recaptures on the square the opponent just captured on, or mate in one. |
| **Miss** | The opponent's previous move gave away ≥ 10% and this move gives back at least half of it (and ≥ 5%), but doesn't drop the mover below where they stood before the gift (minus 5%). Falling further than that is a plain mistake / blunder. |
| **Brilliant** | A best or near-best move (EP loss ≤ *B*) that gives up ≥ 2 points of material, leaves the mover at ≥ 45%, and wasn't needed: the alternative (second-best move, or the best move if this wasn't it) keeps < 90%. |

**Material given up** uses a static exchange evaluation (SEE) built on python-chess legal moves, so pins and x-rays count: after the move, the opponent's best capture sequence on any one square, minus what the move itself captured (`Bxf7+ Kxf7` = 3 − 1 = 2). It only counts as a sacrifice if a safer legal move existed (at least 2 points less given up), so a trapped piece that is lost anyway isn't "sacrificed".

**Rating-dependent thresholds** (Lichess scale, linear between 1000 and 2200, clamped): the Great gap *G* goes from 10% to 15%, and the Brilliant tolerance *B* from 3% to 1%. The EP curve is steeper at higher ratings (the same engine gap costs more expected points), so a fixed gap would make Great fire more often for strong players; the looser Brilliant tolerance at low ratings mirrors Chess.com being more generous with Brilliant there.

Priority: book > brilliant > great > miss > the EP band label. The band label is kept as `base_label`, and the "eval-only review would say…" comparison uses it.

**How often they fire** (`python -m ep_model.scripts.label_stats`, 200 random Lichess games, 13,971 moves, depth 17): Great 2.8%, Miss 1.7%, Brilliant 0.31% of moves. The rates are steady across rating bands (Great 2.6–2.9%, Brilliant 0.25–0.53%, Miss 1.6–2.0%), which is what the rating-dependent thresholds are for.

**multipv=2 cost**, measured on 120 positions at depth 17 (one thread): 0.414 → 0.605 s per position (+46%). The top line's eval moves slightly (median 7.5 cp, 90th percentile 27 cp) compared with the single-line search the model was trained on.

### Coach text

The coach is template text filled from the review. For moves that lost something, a tactic hint is added when one of these checks fires (in this order, `ep_model/phase_d/tactics.py`): **missed mate** (the mover had mate and the move doesn't keep a mate), **allows mate** (the opponent has mate after the move), **hangs a piece** (static exchange after the move wins the opponent at least a pawn net of what the move captured), **missed material** (the best move is a capture that keeps ≥ 2 points after the best recapture). The best move's main line (first 6 plies of the principal variation) is shown under it.

**AI notes (optional).** With `ANTHROPIC_API_KEY` set on the server, an *Explain* button sends Claude (`claude-opus-5-5`, low effort) the facts the review already computed (FEN, move, label, chances, best line, tactic hint) and asks for 2-3 plain sentences that use only those facts. Notes are cached per move and capped at 30 per game; failures (bad key, rate limit, refusal) show a short message in the coach bubble. Without a key the button doesn't appear.

### Retry mode

On a mistake, miss or blunder, the board takes a move for the side that erred (drag, or tap a piece then a square; chess.js checks legality). The engine's best move is accepted instantly. Any other move is scored on the server like a played move (same context row as the real move, eval of the position after the attempt) and counts as correct if it loses ≤ 2% EP against the best move. After two wrong tries the best line is shown. Reviews are kept in a 200-entry in-memory LRU for this; if the server has restarted, the app falls back to accepting the engine's top move (or the second-best if it is within 2%).

### Game rating estimate

"What rating did you play like in this game?" A LightGBM regressor (`ep_model/scripts/fit_rating_estimate.py`, `ep_model/phase_d/rating_estimate.py`) maps one player's moves in one game to their rating. It is fitted on games from the dump that Lichess's servers had already analysed (an eval after every move, known ratings): 200,000 games, 397k player-games with ≥ 10 moves, 20% of games held out.

The features are **rating-free** on purpose: the raw win% drop per move on the Lichess curve (not the EP model, which takes the rating as an input, and not zeroed on the engine's own move, which the fitting data can't know). Per player: mean accuracy, blunder / mistake / inaccuracy / precise-move (< 1%) rates, number of moves, mean |eval|, accuracy in roughly balanced positions (|eval| < 3 pawns) and the share of such moves, time class. The opponent's rating is deliberately left out: matchmaking would make it the best predictor without saying anything about how you played.

| Time class | MAE | Always guess the median | Correlation |
|---|---|---|---|
| Bullet | 332 | 376 | 0.47 |
| Blitz | 292 | 362 | 0.59 |
| Rapid | 252 | 322 | 0.61 |
| Classical | 188 | 238 | 0.61 |

A first version (least squares on accuracy and error rates) only reached blitz MAE 341 vs 364; the balanced-position features did most of the work. One game is still a noisy sample, so the app shows the estimate with ±1 residual SD in the tooltip. For Chess.com games the estimate is mapped back to the Chess.com scale.

### Phase grades

Phases follow Lichess-style material rules: **endgame** once at most 6 queens / rooks / bishops / knights remain; **opening** for the first 10 moves or while still in book; **middlegame** otherwise. Each player's mean move accuracy in a phase becomes a grade shown with the label icons: ≥ 95 best, ≥ 85 excellent, ≥ 75 good, ≥ 60 inaccuracy, ≥ 45 mistake, else blunder (book if every move was book).

**Accuracy** per move uses Lichess's published accuracy curve applied to EP loss in percentage points; a player's accuracy is the mean over their moves. Chess.com's CAPS formula is not public, so numbers are not directly comparable to theirs.

**Eval bar and graph** show white's EP averaged over the actual side-to-move view and a mirrored view of the same position, so the curve doesn't zig-zag with whoever is on move.

## Rating pools

The model learned Lichess ratings. Chess.com ratings run lower, most at the bottom of the range, so Chess.com games are mapped onto the Lichess scale with a simple linear fit per time class (`ep_model/phase_d/ratings.py`). This is an approximation; the summary screen shows the mapped values.

## Known limits

- One month of Lichess data; player populations on other sites differ.
- The harvested pretraining set is self-selected (games someone chose to analyse); fine-tuning on the random clean set corrects the measurable part of that shift, and the test set is drawn only from the clean sample.
- Positions within a game share one label, so the effective sample size is closer to the number of games than the number of positions.
- The model scores positions, not plans: a move that loses chances because of a long-term idea Stockfish sees at depth 17 is judged by that eval.
- Great / Miss / Brilliant are our own documented heuristics, not a claim to match Chess.com's (unpublished) rules.
