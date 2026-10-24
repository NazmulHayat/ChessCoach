# ChessCoach Architecture

The system follows a modular architecture.

Pipeline:

PGN → Game Analyzer → Move Evaluation → Classification → Commentary

---

# Modules

engine/
    stockfish wrapper

analysis/
    game analysis logic

commentary/
    move explanation generation

dataset/
    dataset generation for ML

models/
    training ML models

utils/
    helper utilities

---

# Data Flow

PGN
 ↓
Board positions
 ↓
Stockfish evaluation
 ↓
Centipawn loss
 ↓
Move classification
 ↓
Accuracy calculation
 ↓
Comment generation