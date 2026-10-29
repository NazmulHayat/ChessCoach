# Archive

Earlier work, kept for reference. Nothing here is used by the app or the training pipeline.

| Path | Contents |
|------|----------|
| `move_review/` | The first version: a rule-based Chess.com-style move classifier (PGN → Stockfish → labels by fixed centipawn thresholds), with golden tests and its own Stockfish wrapper (`engine/`). Replaced by the expected-points model. |
| `ep_legacy_scripts/` | One-off scripts from before the sampling stage (replaced by `python -m ep_model.sampling.generate_rows`). |
| `game_rating_experiment/` | A per-move "which rating plays like this?" game-rating experiment (not shipped; see `docs/engineering-log.md`, problem 26). |

Run the old move review from the repository root:

```bash
PYTHONPATH=archive/move_review python archive/move_review/main.py
PYTHONPATH=archive/move_review python archive/move_review/tests/evaluate.py
```
