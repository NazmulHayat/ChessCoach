"""Verify a .pgn.zst file exists in raw/ and print its metadata."""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = _REPO_ROOT / "ep_model" / "raw"

if __name__ == "__main__":
    files = list(RAW_DIR.glob("*.pgn.zst"))
    if not files:
        print("Error: No .pgn.zst file found in ep_model/raw/")
        exit(1)

    path = files[0]
    size_bytes = path.stat().st_size
    size_gb = size_bytes / (1024**3)

    print(f"Full path: {path.resolve()}")
    print(f"Filename:  {path.name}")
    print(f"Size:     {size_bytes:,} bytes")
    print(f"Size:     {size_gb:.2f} GB")
