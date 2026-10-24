import chess
import chess.polyglot
import math
import os
from pathlib import Path

_BOOK_ROOT = Path(__file__).resolve().parent.parent
BOOK_PATH = str(_BOOK_ROOT / "book.bin")

def cp_to_win_prob(cp: float, elo: int = 1500) -> float:
    # rating-adjusted sigmoid — Chess.com customizes this per Elo
    # higher elo = steeper curve (they convert advantages better)
    k = 0.00368208 * (1 + (elo - 1500) / 10000)
    return 1 / (1 + math.exp(-k * cp))

def win_prob_loss(cp_before: float, cp_after: float, 
                  player: chess.Color, elo: int = 1500) -> float:
    if player == chess.WHITE:
        return cp_to_win_prob(cp_before, elo) - cp_to_win_prob(cp_after, elo)
    else:
        return cp_to_win_prob(-cp_before, elo) - cp_to_win_prob(-cp_after, elo)

def is_book_move(board: chess.Board, move: chess.Move) -> bool:
    """Match any opening book entry, not just highest-weight."""
    if not os.path.exists(BOOK_PATH):
        return False
    try:
        with chess.polyglot.open_reader(BOOK_PATH) as reader:
            for entry in reader.find_all(board):
                if entry.move == move:
                    return True
            return False
    except (KeyError, IndexError, OSError):
        return False

def is_brilliant(board: chess.Board, move: chess.Move, best_move: chess.Move,
                 cp_before: float, cp_after: float, player: chess.Color) -> bool:
    # must be best move
    if move != best_move:
        return False

    piece_values = {
        chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
        chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0
    }

    moving_piece = board.piece_at(move.from_square)
    captured_piece = board.piece_at(move.to_square)

    if not moving_piece:
        return False

    moving_val = piece_values.get(moving_piece.piece_type, 0)
    captured_val = piece_values.get(captured_piece.piece_type, 0) if captured_piece else 0

    # must be a sacrifice
    is_sacrifice = moving_val > captured_val

    # eval must improve ~1.5 pawns (Chess.com Brilliant definition)
    if player == chess.WHITE:
        eval_improves = cp_after > cp_before + 150
    else:
        eval_improves = cp_after < cp_before - 150

    # must not be already winning before the move
    wp_before = cp_to_win_prob(cp_before if player == chess.WHITE else -cp_before, 1500)
    not_already_winning = wp_before < 0.90

    return is_sacrifice and eval_improves and not_already_winning

def _multipv_gap(eval_before: dict) -> float:
    """Gap between 1st and 2nd best in same position (cp)."""
    multipv = eval_before.get("multipv", [])
    if len(multipv) < 2:
        return float("inf")  # no alternative, treat as large gap
    return abs(multipv[0]["cp"] - multipv[1]["cp"])


def is_great(move: chess.Move, best_move: chess.Move,
             cp_before: float, cp_after: float,
             eval_before: dict, player: chess.Color) -> bool:
    """Only equalizes/punishes — Chess.com uses Great sparingly (0-2 per game)."""
    if move != best_move:
        return False

    # "The only good move" — very large gap only (Chess.com rarely uses this)
    gap = _multipv_gap(eval_before)
    if gap >= 300:
        return True

    # Equalizes losing position or punishes opponent's mistake
    if player == chess.WHITE:
        was_struggling = cp_before < 50
        now_better = cp_after > cp_before + 150
    else:
        was_struggling = cp_before > -50
        now_better = cp_after < cp_before - 150

    return was_struggling and now_better


def _allows_forced_mate(cp_after: float, player: chess.Color) -> bool:
    """Opponent has forced mate after our move."""
    if player == chess.WHITE:
        return cp_after < -4000  # black mating
    return cp_after > 4000  # white mating


def _loses_material(board: chess.Board, move: chess.Move, player: chess.Color) -> bool:
    """Check if move leaves a piece hanging (attacked, not defended)."""
    piece_values = {
        chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
        chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0
    }
    board.push(move)
    try:
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if not piece or piece.color != player:
                continue
            attackers = board.attackers(not player, square)
            defenders = board.attackers(player, square)
            if not attackers:
                continue
            # Hanging: attacked and not defended, or attacked by lower value
            min_attacker_val = min(
                piece_values.get(board.piece_at(sq).piece_type, 0)
                for sq in attackers if board.piece_at(sq)
            )
            if not defenders or min_attacker_val < piece_values.get(piece.piece_type, 0):
                return True
        return False
    finally:
        board.pop()


def classify_move(
    cp_before: float,
    cp_after: float,
    board: chess.Board,
    move: chess.Move,
    eval_before: dict,
    player: chess.Color,
    elo: int = 1500,
    prev_opponent_classification: str | None = None
) -> str:
    """Classify move per Chess.com Game Review logic."""
    best_move = eval_before["best_move"]
    wpl = win_prob_loss(cp_before, cp_after, player, elo)

    # book first
    if is_book_move(board, move):
        return "Book"

    # brilliant
    if is_brilliant(board, move, best_move, cp_before, cp_after, player):
        return "Brilliant"

    # great
    if is_great(move, best_move, cp_before, cp_after, eval_before, player):
        return "Great"

    # miss — opponent blundered/mistake last move, you failed to exploit
    opponent_error = prev_opponent_classification in ("Mistake", "Blunder")
    if opponent_error and move != best_move and wpl > 0.05:
        return "Miss"

    # best — engine top move (multipv gap >= 30cp per Chess.com)
    multipv_gap = _multipv_gap(eval_before)
    if move == best_move:
        if multipv_gap >= 30:
            return "Best"
        return "Excellent"  # top move but alternatives nearly equal

    # WPL thresholds (calibrated to match Chess.com expected)
    if wpl <= 0.02:
        return "Excellent"
    if wpl <= 0.05:
        return "Good"
    if wpl <= 0.10:
        return "Inaccuracy"
    if wpl <= 0.20:
        return "Mistake"
    # Blunder: WPL>0.20 AND (loses material OR allows forced mate)
    # Positional-only eval drops → Mistake
    concrete_consequence = _allows_forced_mate(cp_after, player) or _loses_material(
        board, move, player
    )
    if wpl > 0.20 and concrete_consequence:
        return "Blunder"
    return "Mistake"