import pytest
from pathlib import Path

@pytest.fixture
def tmp_state_dir(tmp_path: Path) -> Path:
    d = tmp_path / "state"
    d.mkdir()
    (d / "snapshots").mkdir()
    return d
