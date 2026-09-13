"""Exercise only the installed denial finder, never actual heavy package code."""
import importlib
import sys
import pytest


def test_ten_heavy_roots_are_refused_before_discovery():
    guard = sys.modules['_scratch.agw_heavy_import_guard']
    assert sys.meta_path[0] is guard._finder
    for name in sorted(guard.BLOCKED):
        assert name not in sys.modules
        with pytest.raises(ImportError, match='Synthetic guard forbids actual heavy import'):
            importlib.import_module(name)
        assert name not in sys.modules
