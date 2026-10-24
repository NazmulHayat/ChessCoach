"""safe_run CLI smoke (no Stockfish)."""

import pytest

pytest.importorskip("psutil")

from ep_model.scripts import safe_run


def test_safe_run_dry_run():
    rc = safe_run.main(["--dry-run"])
    assert rc == 0
