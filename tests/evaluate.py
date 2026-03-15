import json
import os

def compare(actual: dict, expected: dict, game_name: str):
    print(f"\n{'='*40}")
    print(f"  {game_name}")
    print(f"{'='*40}")

    # accuracy diff
    wa_diff = actual["white_accuracy"] - expected["white_accuracy"]
    ba_diff = actual["black_accuracy"] - expected["black_accuracy"]
    print(f"\nAccuracy:")
    print(f"  White: ours={actual['white_accuracy']}  expected={expected['white_accuracy']}  diff={wa_diff:+.1f}")
    print(f"  Black: ours={actual['black_accuracy']}  expected={expected['black_accuracy']}  diff={ba_diff:+.1f}")

    # rating diff
    wr_diff = actual["white_rating"] - expected["white_rating"]
    br_diff = actual["black_rating"] - expected["black_rating"]
    print(f"\nGame Rating:")
    print(f"  White: ours={actual['white_rating']}  expected={expected['white_rating']}  diff={wr_diff:+}")
    print(f"  Black: ours={actual['black_rating']}  expected={expected['black_rating']}  diff={br_diff:+}")

    # classification diff
    categories = ["Brilliant", "Great", "Book", "Best", "Excellent",
                  "Good", "Inaccuracy", "Mistake", "Miss", "Blunder"]
    print(f"\n{'Category':<12} {'W_ours':>6} {'W_exp':>6} {'W_diff':>7}  {'B_ours':>6} {'B_exp':>6} {'B_diff':>7}")
    print("-" * 60)
    for cat in categories:
        wo = actual["white"].get(cat, 0)
        we = expected["white"].get(cat, 0)
        bo = actual["black"].get(cat, 0)
        be = expected["black"].get(cat, 0)
        print(f"{cat:<12} {wo:>6} {we:>6} {wo-we:>+7}  {bo:>6} {be:>6} {bo-be:>+7}")


# --- run ---
games = [
    ("tests/game1_actual.json", "tests/game1_expected.json", "Game 1"),
    ("tests/game2_actual.json", "tests/game2_expected.json", "Game 2"),
]

for actual_path, expected_path, name in games:
    if not os.path.exists(actual_path):
        print(f"\nSkipping {name} — {actual_path} not found")
        continue
    if not os.path.exists(expected_path):
        print(f"\nSkipping {name} — {expected_path} not found")
        continue

    with open(actual_path) as f:
        actual = json.load(f)
    with open(expected_path) as f:
        expected = json.load(f)

    compare(actual, expected, name)