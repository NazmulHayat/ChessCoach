# ChessCoach — Project Context

## What
Python tool that analyzes chess games like Chess.com Game Review.
Input: PGN file. Output: move classifications, accuracy, game rating, commentary.

## Data Flow
```
PGN → parse_pgn() → positions[], moves[], elos
  → get_evals(positions) → evals[] (cp, best_move, multipv, depth)
  → classify_move() per move → labels (Book/Brilliant/Great/Miss/Best/Excellent/Good/Inaccuracy/Mistake/Blunder)
  → calculate_accuracy() → CAPS2 score per player
  → calculate_game_rating() → performance Elo per player
  → output JSON + console summary
```

## Current State
Working: parser, engine, classifier (with bugs), accuracy formula, JSON output.
Empty/TODO: `metrics/accuracy.py`, `metrics/phases.py`, `output/report.py`, `llm/explainer.py`.

## Known Bugs
See `docs/chess_com_classification_research.md` § "Code Bugs" for details.
