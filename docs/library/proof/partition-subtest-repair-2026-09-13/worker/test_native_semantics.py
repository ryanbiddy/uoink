"""Deliberate inert outcomes; no product imports, network or application work."""
import unittest
import pytest


class TestUnittestSubtests(unittest.TestCase):
    def test_pass_repeated(self):
        for _ in range(2):
            with self.subTest("same", value="repeated"):
                self.assertTrue(True)

    def test_failed(self):
        with self.subTest("failed", value=1):
            self.assertEqual(1, 2)
        with self.subTest("passed", value=2):
            self.assertTrue(True)

    def test_skipped(self):
        with self.subTest("skip", value=1):
            self.skipTest("intentional subtest skip")
        with self.subTest("passed", value=2):
            self.assertTrue(True)

    def test_nested(self):
        with self.subTest("outer", level=1):
            with self.subTest("inner", level=2):
                self.assertEqual(1, 2)

    def test_parent_failure(self):
        with self.subTest("child fails"):
            self.assertEqual(1, 2)
        self.fail("intentional parent failure")


@pytest.fixture
def bad_teardown():
    yield None
    raise RuntimeError("intentional teardown failure")


def test_pytest_pass(subtests):
    for value in range(2):
        with subtests.test("pass", value=value):
            assert True


def test_pytest_failed(subtests):
    with subtests.test("failed", value=1):
        assert False, "intentional subtest failure"
    with subtests.test("passed", value=2):
        assert True


def test_pytest_skipped(subtests):
    with subtests.test("skip", value=1):
        pytest.skip("intentional subtest skip")


def test_pytest_parent_failure(subtests):
    with subtests.test("child fails"):
        assert False, "intentional subtest failure"
    assert False, "intentional parent failure"


def test_pytest_parent_and_teardown(subtests, bad_teardown):
    with subtests.test("child fails"):
        assert False, "intentional subtest failure"
    assert False, "intentional parent failure"


def test_pytest_subtest_and_teardown(subtests, bad_teardown):
    with subtests.test("child fails"):
        assert False, "intentional subtest failure"


def test_pytest_pass_and_teardown(subtests, bad_teardown):
    with subtests.test("child passes"):
        assert True


def test_pytest_subtest_and_parent_skip(subtests):
    with subtests.test("child fails"):
        assert False, "intentional subtest failure"
    pytest.skip("intentional parent skip")
