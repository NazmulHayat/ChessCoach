# ChessCoach

Expected-points (EP) model training from Lichess dumps, then move review and product layers on top.

## Active layout

| Path | Role |
|------|------|
| `ep_model/` | EP pipeline: Phase A → B → C (LightGBM). See `ep_model/TRAINING_PLAN.md` and `ep_model/README.md`. |
| `engine/` | Shared UCI Stockfish wrapper (used by EP Phase B and archived move-review). |
| `tests/` | Active tests (e.g. `test_ep_phase_a_rowgen.py`). |

## Quick start (EP)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m ep_model.phase_a.generate_rows --max-games 2000
python -m ep_model.phase_b.augment_evals --max-rows 3000 -v
python -m ep_model.phase_c.train -v
# Long Phase B on a laptop: batched runner + background engine policy (see ep_model/README.md)
# python -m ep_model.scripts.safe_run
```

Place Lichess `*.pgn.zst` under `ep_model/raw/` (see `ep_model/README.md`).

## Archived code

Older move-classification / docs / one-off scripts are under `archive/` (see `archive/README.md`). They stay in git for reference; Cursor ignores that folder via `.cursorignore`.
