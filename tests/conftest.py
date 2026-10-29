"""Pytest: ensure repo root is on sys.path for `ep_model` imports."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# PyTorch tests run in their own process (tests/test_training_nn.py): torch and LightGBM each bundle
# an OpenMP runtime, and on macOS loading both in one process aborts it.
collect_ignore = ["torch_only"]
