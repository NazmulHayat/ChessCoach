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

- Source: one Lichess monthly rated-games dump (February 2026), streamed without decompressing to disk.
- About 5 random positions per game, so no single game dominates and positions are spread over the whole game.
- Label: the final game result from the side to move's point of view. Every sampled position of a game shares that game's result, which is the standard setup for "from this position, how did it end".

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

Baseline 4 is the important comparison: the gap between it and the EP model is the value of the context features, with model capacity held equal. The report also breaks results down by rating band and time class and includes a calibration table.

## From EP to move labels

For each move the review computes:

- **EP if best**: the mover's EP had they played Stockfish's best move.
- **EP after**: the mover's EP after the move actually played.
- **EP loss** = max(0, EP if best − EP after).

Both numbers are scored on an *opponent-to-move* row with identical context (same ply, clocks, ratings), differing only in the engine eval. The model has a small side-to-move bias; comparing like with like cancels it. An earlier version compared "before the move" with "after the move" directly, and that bias showed up as a fake ~20% loss on every move.

Labels then use Chess.com's published bands: best (engine move), excellent < 0.02, good < 0.05, inaccuracy < 0.10, mistake < 0.20, blunder ≥ 0.20. Book moves come from a polyglot opening book. The same bands applied to the Lichess win% curve give the "eval-only" label the coach compares against.

**Accuracy** per move uses Lichess's published accuracy curve applied to EP loss in percentage points; a player's accuracy is the mean over their moves. Chess.com's CAPS formula is not public, so numbers are not directly comparable to theirs.

**Eval bar and graph** show white's EP averaged over the actual side-to-move view and a mirrored view of the same position, so the curve doesn't zig-zag with whoever is on move.

## Rating pools

The model learned Lichess ratings. Chess.com ratings run lower, most at the bottom of the range, so Chess.com games are mapped onto the Lichess scale with a simple linear fit per time class (`ep_model/phase_d/ratings.py`). This is an approximation; the summary screen shows the mapped values.

## Known limits

- One month of Lichess data; player populations on other sites differ.
- Positions within a game share one label, so the effective sample size is closer to the number of games than the number of positions.
- The model scores positions, not plans: a move that loses chances because of a long-term idea Stockfish sees at depth 17 is judged by that eval.
- Great / Miss / Brilliant labels are not implemented yet; when they are, they will be our own documented heuristics, not a claim to match Chess.com exactly.
