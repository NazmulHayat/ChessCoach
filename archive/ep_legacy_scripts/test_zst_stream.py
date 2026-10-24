"""Test streaming decompression of a .pgn.zst file."""

from pathlib import Path
import zstandard

_REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = _REPO_ROOT / "ep_model" / "raw"

if __name__ == "__main__":
    files = list(RAW_DIR.glob("*.pgn.zst"))
    if not files:
        print("Error: No .pgn.zst file found in ep_model/raw/")
        exit(1)

    path = files[0]
    print(f"Streaming first 30 lines from: {path.name}\n")

    with zstandard.open(path, "rt") as f:
        for i, line in enumerate(f):
            if i >= 30:
                break
            print(line, end="")
