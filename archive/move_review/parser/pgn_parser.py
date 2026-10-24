import chess.pgn
import chess

def parse_pgn(file_path):
    game = chess.pgn.read_game(open(file_path))
    board = game.board()

    # extract ratings from headers
    white_elo = int(game.headers.get("WhiteElo", 1500))
    black_elo = int(game.headers.get("BlackElo", 1500))

    positions = []
    moves = []

    positions.append(board.copy())

    for move in game.mainline_moves():
        moves.append({
            "move": move,
            "player": board.turn,
            "move_number": board.fullmove_number
        })
        board.push(move)
        positions.append(board.copy())

    return positions, moves, white_elo, black_elo