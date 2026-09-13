"""Deliberate inert failures for receipt accounting; never product acceptance."""
import pytest


@pytest.fixture
def teardown_failure():
    yield
    pytest.fail('Deliberate inert teardown failure for receipt accounting')


def test_ordinary_pass_is_retained():
    assert 2 + 2 == 4


def test_call_and_teardown_failures_are_both_retained(teardown_failure):
    pytest.fail('Deliberate inert call failure for receipt accounting')
