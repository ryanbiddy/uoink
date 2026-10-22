import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def isolated_usage_store(tmp_path, monkeypatch):
    """Every test, including settings readers, uses disposable usage state."""
    import uoink_usage
    uoink_usage.flush()
    root = lambda: tmp_path / "usage"
    monkeypatch.setattr(uoink_usage, "_root", root)
    configure = uoink_usage.configure
    # A late server import also calls configure. It must not undo isolation.
    monkeypatch.setattr(uoink_usage, "configure", lambda _, version, install_kind="source":
                        configure(root, version, install_kind))
    monkeypatch.setenv("UOINK_USAGE_ENDPOINT", "")

    def no_send(*args, **kwargs):
        raise AssertionError("Usage sends must be mocked")

    monkeypatch.setattr(uoink_usage, "_post", no_send)
    yield
    assert uoink_usage.flush(timeout=6), "usage counts did not finish in the test store"


@pytest.fixture
def tmp(tmp_path: Path) -> Path:
    return tmp_path
