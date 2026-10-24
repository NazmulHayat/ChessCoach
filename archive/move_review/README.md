# Move review (archived)

Chess.com–like game review: parse PGN, run Stockfish (`engine/` at repo root), classify moves, compare against `tests/*_expected.json`.

Requires Stockfish on `PATH` as `stockfish` (see `engine/stockfish_engine.py`).

```bash
# From repository root
PYTHONPATH=. python archive/move_review/main.py archive/move_review/pgns/game1.pgn
PYTHONPATH=. python archive/move_review/tests/evaluate.py
```
