import chess
import chess.polyglot
import math
import os

BOOK_PATH = "book.bin"

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
    if not os.path.exists(BOOK_PATH):
        return False
    try:
        with chess.polyglot.open_reader(BOOK_PATH) as reader:
            entry = reader.find(board)
            return entry.move == move
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

    # eval must improve significantly
    if player == chess.WHITE:
        eval_improves = cp_after > cp_before + 100
    else:
        eval_improves = cp_after < cp_before - 100

    # must not be already winning before the move
    wp_before = cp_to_win_prob(cp_before if player == chess.WHITE else -cp_before)
    not_already_winning = wp_before < 0.90

    return is_sacrifice and eval_improves and not_already_winning

def is_great(move: chess.Move, best_move: chess.Move,
             cp_before: float, cp_after: float,
             evals: list, player: chess.Color) -> bool:
    # great = only winning move OR saves a lost/equal game
    if move != best_move:
        return False

    # only move — big gap between best and second best
    if len(evals) >= 2:
        gap = abs(evals[0]["cp"] - evals[1]["cp"])
        if gap > 150:
            return True

    # saves the game — position was lost/equal before, winning after
    if player == chess.WHITE:
        was_struggling = cp_before < 50    # was equal or worse
        now_better = cp_after > cp_before + 150  # now clearly better
    else:
        was_struggling = cp_before > -50
        now_better = cp_after < cp_before - 150

    return was_struggling and now_better

def classify_move(
    cp_before: float,
    cp_after: float,
    board: chess.Board,
    move: chess.Move,
    evals: list,
    player: chess.Color,
    elo: int = 1500
) -> str:
    best_move = evals[0]["best_move"]
    wpl = win_prob_loss(cp_before, cp_after, player, elo)

    # book first
    if is_book_move(board, move):
        return "Book"

    # brilliant
    if is_brilliant(board, move, best_move, cp_before, cp_after, player):
        return "Brilliant"

    # great
    if is_great(move, best_move, cp_before, cp_after, evals, player):
        return "Great"

    # miss — clearly winning but didn't convert
    wp_before = cp_to_win_prob(cp_before if player == chess.WHITE else -cp_before, elo)
    if wp_before >= 0.85 and move != best_move and wpl > 0.10:
        return "Miss"

    # best = exact engine move with no loss
    if move == best_move:
        return "Best"

    # WPL thresholds (Chess.com standard)
    elif wpl <= 0.02: return "Excellent"
    elif wpl <= 0.05: return "Good"
    elif wpl <= 0.10: return "Inaccuracy"
    elif wpl <= 0.20: return "Mistake"
    else:             return "Blunder"