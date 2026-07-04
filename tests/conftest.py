import pytest
from pathlib import Path

@pytest.fixture
def tmp(tmp_path: Path) -> Path:
    return tmp_path
