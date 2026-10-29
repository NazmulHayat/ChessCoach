"""Runs tests/torch_only in a separate pytest process (see conftest.py for why)."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(importlib.util.find_spec("torch") is None, reason="torch not installed")
def test_torch_only_suite():
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--rootdir", str(_ROOT), str(_ROOT / "tests" / "torch_only")],
        cwd=_ROOT,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
