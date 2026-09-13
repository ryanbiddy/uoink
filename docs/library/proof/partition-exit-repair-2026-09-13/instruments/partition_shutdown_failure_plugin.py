"""Raise only at pytest shutdown, after ordinary results and session receipt."""
import pytest


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    raise RuntimeError('Deliberate inert shutdown error after completed case reports')
