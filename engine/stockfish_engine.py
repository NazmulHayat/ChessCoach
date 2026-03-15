import chess
import chess.engine

STOCKFISH_PATH = "stockfish"

def get_evals(positions: list) -> list:
    evals = []

    with chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH) as engine:
        engine.configure({"Threads": 4, "Hash": 256})

        for i, board in enumerate(positions):
            print(f"Analysing position {i+1}/{len(positions)}...")

            info = engine.analyse(
                board,
                chess.engine.Limit(nodes=500000),  # Chess.com style — nodes not depth
                multipv=3
            )

            best = info[0]
            score = best["score"].white()

            if score.is_mate():
                mate_in = score.mate()
                cp = 10000 if mate_in > 0 else -10000
            else:
                cp = score.score()

            evals.append({
                "cp": cp,
                "best_move": best["pv"][0] if "pv" in best else None,
                "pv": best["pv"] if "pv" in best else [],
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