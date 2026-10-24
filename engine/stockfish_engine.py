import chess
import chess.engine

STOCKFISH_PATH = "stockfish"

# Chess.com Game Review settings (node-based, not depth)
# - Chess.com uses nodes, not depth; Standard ≈ 3430 rating (~depth 20-22)
# - Fast: 200k | Standard: 500k-1M | Deep: 2M+ nodes
# - Time alternative: Limit(time=10) for ~10 sec/move
NODES_PER_POSITION = 500_000
THREADS = 4
HASH_MB = 256

def get_evals(positions: list) -> list:
    evals = []

    with chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH) as engine:
        engine.configure({"Threads": THREADS, "Hash": HASH_MB})

        for i, board in enumerate(positions):
            print(f"Analysing position {i+1}/{len(positions)}...")

            # Chess.com uses node-based analysis; multipv=3 for Great/Best detection
            info_list = engine.analyse(
                board,
                chess.engine.Limit(nodes=NODES_PER_POSITION),
                multipv=3
            )

            def _mate_to_cp(mate_in: int) -> int:
                """Finer gradation: mate-in-1 ≠ mate-in-20."""
                sign = 1 if mate_in > 0 else -1
                return sign * (10000 - abs(mate_in) * 100)

            multipv_lines = []
            for inf in info_list:
                score = inf["score"].white()
                if score.is_mate():
                    cp = _mate_to_cp(score.mate())
                else:
                    cp = score.score()
                move = inf["pv"][0] if "pv" in inf else None
                multipv_lines.append({"cp": cp, "move": move})

            best = info_list[0]
            score = best["score"].white()
            if score.is_mate():
                cp = _mate_to_cp(score.mate())
            else:
                cp = score.score()

            evals.append({
                "cp": cp,
                "best_move": best["pv"][0] if "pv" in best else None,
                "multipv": multipv_lines,
                "depth": best.get("depth", 0)
            })

    return evals


def calculate_cpl(eval_before: dict, eval_after: dict, player: chess.Color) -> float:
    before = eval_before["cp"]
    after = eval_after["cp"]

    if player == chess.WHITE:
        cpl = before - after
    else:
        cpl = after - before

    return max(0, cpl)