# Archive

Legacy and paused work lives here so the repo root stays focused on **EP model training** (`ep_model/`) and shared engine code (`engine/`).

| Path | Contents |
|------|----------|
| `move_review/` | Chess.com–style move classification pipeline (PGN → Stockfish → labels), golden tests, polyglot `book.bin`, old docs |
| `ep_legacy_scripts/` | Pre–Phase A one-off scripts (replaced by `python -m ep_model.phase_a.generate_rows`) |

Restore or copy pieces back to the project root when you resume that work. Run move-review tools from the **repository root** with `PYTHONPATH` set so `engine/` resolves:

```bash
cd /path/to/ChessCoach
PYTHONPATH=. python archive/move_review/main.py
PYTHONPATH=. python archive/move_review/tests/evaluate.py
```

The `.cursorignore` file excludes `archive/` from Cursor indexing so day-to-day work stays on active paths.
