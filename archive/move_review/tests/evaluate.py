import json
import os

def compare(actual: dict, expected: dict, game_name: str) -> int:
    """Returns total absolute diff across all metrics."""
    print(f"\n{'='*40}")
    print(f"  {game_name}")
    print(f"{'='*40}")

    total_diff = 0

    # accuracy diff
    wa_diff = actual["white_accuracy"] - expected["white_accuracy"]
    ba_diff = actual["black_accuracy"] - expected["black_accuracy"]
    total_diff += abs(wa_diff) + abs(ba_diff)
    print(f"\nAccuracy:")
    print(f"  White: ours={actual['white_accuracy']}  expected={expected['white_accuracy']}  diff={wa_diff:+.1f}")
    print(f"  Black: ours={actual['black_accuracy']}  expected={expected['black_accuracy']}  diff={ba_diff:+.1f}")

    # rating diff
    wr_diff = actual["white_rating"] - expected["white_rating"]
    br_diff = actual["black_rating"] - expected["black_rating"]
    total_diff += abs(wr_diff) + abs(br_diff)
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
        total_diff += abs(wo - we) + abs(bo - be)
        print(f"{cat:<12} {wo:>6} {we:>6} {wo-we:>+7}  {bo:>6} {be:>6} {bo-be:>+7}")
    print(f"\n  Total abs diff: {total_diff}")
    return total_diff


# --- run ---
# Auto-discover all game*_actual.json files and match with expected
tests_dir = os.path.dirname(os.path.abspath(__file__))
actual_files = sorted(f for f in os.listdir(tests_dir) if f.endswith("_actual.json"))
games = []
for af in actual_files:
    ef = af.replace("_actual.json", "_expected.json")
    actual_path = os.path.join(tests_dir, af)
    expected_path = os.path.join(tests_dir, ef)
    name = af.replace("_actual.json", "").replace("game", "Game ")
    games.append((actual_path, expected_path, name))

grand_total = 0
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

    grand_total += compare(actual, expected, name)

print(f"\n{'='*40}")
print(f"  GRAND TOTAL ABS DIFF: {grand_total}")
print(f"{'='*40}")