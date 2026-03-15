import chess
import math
import sys
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

    return round(max(0, min(100, accuracy)), 1)

def calculate_game_rating(accuracy: float, opponent_elo: int) -> int:
    # map accuracy to expected score properly
    # 100% accuracy = win, 50% accuracy = draw, 0% = loss
    win_chance = (accuracy - 50) / 50  # -1 to +1 scale
    performance = opponent_elo + 400 * win_chance
    return round(max(100, min(3000, performance)))

# --- run ---
pgn_path = sys.argv[1] if len(sys.argv) > 1 else "pgns/game1.pgn"
positions, moves, white_elo, black_elo = parse_pgn(pgn_path)
evals = get_evals(positions)

classifications = []

for i, move_data in enumerate(moves):
    cp_before = evals[i]["cp"]
    cp_after = evals[i+1]["cp"]
    elo = white_elo if move_data["player"] == chess.WHITE else black_elo
    label = classify_move(
        cp_before, cp_after,
        positions[i], move_data["move"],
        evals[i:i+3], move_data["player"],
        elo
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


import json

actual = {
    "white_accuracy": white_acc,
    "black_accuracy": black_acc,
    "white_rating": white_rating,
    "black_rating": black_rating,
    "white": dict(white),
    "black": dict(black)
}

output_path = pgn_path.replace("pgns/", "tests/").replace(".pgn", "_actual.json")
with open(output_path, "w") as f:
    json.dump(actual, f, indent=2)
print(f"\nSaved to {output_path}")