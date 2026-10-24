"""Parse and print headers of the first PGN game from a .pgn.zst file."""

from pathlib import Path
import zstandard
import chess.pgn

_REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = _REPO_ROOT / "ep_model" / "raw"

HEADERS = [
    "Event",
    "Site",
    "Date",
    "White",
    "Black",
    "WhiteElo",
    "BlackElo",
    "Result",
    "TimeControl",
    "Opening",
]

if __name__ == "__main__":
    files = list(RAW_DIR.glob("*.pgn.zst"))
    if not files:
        print("Error: No .pgn.zst file found in ep_model/raw/")
        exit(1)

    with zstandard.open(files[0], "rt") as f:
        game = chess.pgn.read_game(f)

    if game is None:
        print("Error: No game found in file")
        exit(1)

    for h in HEADERS:
        val = game.headers.get(h, "(not set)")
        print(f"{h}: {val}")
