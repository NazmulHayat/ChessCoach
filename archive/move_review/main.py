import chess
import json
import math
import sys
from pathlib import Path

from parser.pgn_parser import parse_pgn
from engine.stockfish_engine import get_evals
from classification.move_classifier import classify_move, win_prob_loss
from collections import Counter

def calculate_accuracy(evals: list, moves: list, 
                        player: chess.Color, elo: int) -> float:
    wpl_list = []
    for i, move_data in enumerate(moves):
        if move_data["player"] != player:
            continue
        cp_before = evals[i]["cp"]
        cp_after = evals[i+1]["cp"]
        wpl = win_prob_loss(cp_before, cp_after, player, elo)
        wpl_list.append(max(0, wpl * 100))

    if not wpl_list:
        return 0.0

    avg_wpl = sum(wpl_list) / len(wpl_list)

    # Chess.com CAPS2 formula
    accuracy = 103.1668 * math.exp(-0.04354 * avg_wpl) - 3.1669
    # Scale down: our engine tends to give higher accuracy than Chess.com
    accuracy = 50 + (accuracy - 50) * 0.88

    return round(max(0, min(100, accuracy)), 1)

# Conservative accuracy → Elo. Our accuracy tends higher than Chess.com's
# (different engine), so use flatter curve: 92%→~2100, 100%→~2200
_ACCURACY_TO_ELO = [(55, 1000), (68, 1500), (80, 2000), (100, 2200)]


def calculate_game_rating(accuracy: float, opponent_elo: int) -> int:
    """Calibrated to match Chess.com Game Review ratings."""
    if accuracy <= _ACCURACY_TO_ELO[0][0]:
        return 1000
    if accuracy >= _ACCURACY_TO_ELO[-1][0]:
        return 2200
    for i in range(len(_ACCURACY_TO_ELO) - 1):
        a1, e1 = _ACCURACY_TO_ELO[i]
        a2, e2 = _ACCURACY_TO_ELO[i + 1]
        if a1 <= accuracy <= a2:
            t = (accuracy - a1) / (a2 - a1)
            pure = e1 + t * (e2 - e1)
            # Blend with opponent to avoid overshooting when our accuracy is inflated
            blended = 0.7 * pure + 0.3 * opponent_elo
            r = max(100, min(3000, blended))
            return round(r / 100) * 100  # Chess.com: 1800, 1900, 2000, etc.
    return 1500


_ROOT = Path(__file__).resolve().parent

# --- run ---
pgn_path = Path(sys.argv[1]) if len(sys.argv) > 1 else _ROOT / "pgns" / "game1.pgn"
pgn_path = pgn_path.expanduser()
if not pgn_path.is_absolute():
    pgn_path = Path.cwd() / pgn_path
pgn_path = pgn_path.resolve()

positions, moves, white_elo, black_elo = parse_pgn(str(pgn_path))
evals = get_evals(positions)

classifications = []

for i, move_data in enumerate(moves):
    cp_before = evals[i]["cp"]
    cp_after = evals[i + 1]["cp"]
    elo = white_elo if move_data["player"] == chess.WHITE else black_elo
    prev_opp = classifications[i - 1][1] if i > 0 and moves[i - 1]["player"] != move_data["player"] else None
    label = classify_move(
        cp_before, cp_after,
        positions[i], move_data["move"],
        evals[i], move_data["player"],
        elo,
        prev_opponent_classification=prev_opp
    )
    classifications.append((move_data["player"], label))
    print(f"Move {move_data['move_number']} {move_data['move']}: {label}")

# --- summary ---
white = Counter(label for player, label in classifications if player == chess.WHITE)
black = Counter(label for player, label in classifications if player == chess.BLACK)

white_acc = calculate_accuracy(evals, moves, chess.WHITE, white_elo)
black_acc = calculate_accuracy(evals, moves, chess.BLACK, black_elo)

white_rating = calculate_game_rating(white_acc, black_elo)
black_rating = calculate_game_rating(black_acc, white_elo)

categories = ["Brilliant", "Great", "Book", "Best", "Excellent", 
              "Good", "Inaccuracy", "Mistake", "Miss", "Blunder"]

print(f"\nAccuracy  — White: {white_acc}    Black: {black_acc}")
print(f"Game Rating — White: {white_rating}   Black: {black_rating}\n")
print("{:<12} {:>6} {:>6}".format("", "White", "Black"))
print("-" * 26)
for cat in categories:
    print("{:<12} {:>6} {:>6}".format(cat, white.get(cat, 0), black.get(cat, 0)))


actual = {
    "white_accuracy": white_acc,
    "black_accuracy": black_acc,
    "white_rating": white_rating,
    "black_rating": black_rating,
    "white": dict(white),
    "black": dict(black)
}

output_path = _ROOT / "tests" / f"{pgn_path.stem}_actual.json"
with open(output_path, "w") as f:
    json.dump(actual, f, indent=2)
print(f"\nSaved to {output_path}")