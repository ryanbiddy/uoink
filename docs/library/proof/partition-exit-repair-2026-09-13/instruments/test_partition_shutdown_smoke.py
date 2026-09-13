"""Green case followed by a separate deliberate plugin shutdown error."""


def test_completed_case_remains_passed():
    assert 'receipt'.upper() == 'RECEIPT'
