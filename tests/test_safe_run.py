"""safe_run CLI smoke (no Stockfish)."""

import pytest

pytest.importorskip("psutil")

from ep_model.scripts import safe_run


def test_safe_run_dry_run():
    # Loose health limits: the guard reads this machine's real swap and disk, which shouldn't decide the test.
    rc = safe_run.main(["--dry-run", "--max-swap-gib", "1000", "--min-free-gib", "0"])
    assert rc == 0
