"""Regression tests for isolated credential-store namespace and ordinary compatibility.

Verifies:
1. Isolated read, set, delete operations select the deterministic profile-derived service.
2. Absent key in isolated mode never falls back to ordinary Uoink or legacy Yoink.
3. Profile separation: two profiles sharing a port do not share credentials.
4. Stable profile identity: a profile changing port retains its credentials.
5. Ordinary legacy compatibility: non-isolated mode retains existing Uoink/Yoink behavior.
6. 401 / invalid key reset clears only the isolated credential namespace.
7. Public settings reflects isolated key state without calling ordinary services.
8. Plaintext settings.json migration writes exclusively to the isolated namespace.
9. Every isolated test asserts no calls to ordinary services ("Uoink", "Yoink").
10. No paid key environment variables are set or used.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import pytest

import uoink_install_isolation as iso
import server


class RecordingFakeKeyring:
    """Recording fake keyring backend for testing credential storage."""

    def __init__(self) -> None:
        self.passwords: dict[tuple[str, str], str] = {}
        self.calls: list[dict[str, str]] = []

    def get_password(self, service: str, username: str) -> str | None:
        self.calls.append({"op": "get", "service": service, "username": username})
        return self.passwords.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        # Do not log or persist raw key material in calls
        self.calls.append({"op": "set", "service": service, "username": username})
        self.passwords[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.calls.append({"op": "delete", "service": service, "username": username})
        if (service, username) in self.passwords:
            del self.passwords[(service, username)]
        else:
            raise Exception(f"Password not found for service={service!r} username={username!r}")


def _expected_isolated_service(profile: Path) -> str:
    canonical = os.path.normcase(os.path.normpath(str(profile.resolve())))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return f"Uoink-isolated-{digest}"


def assert_no_ordinary_service_calls(fake_kr: RecordingFakeKeyring) -> None:
    """Assert that no operation accessed ordinary 'Uoink' or legacy 'Yoink' services."""
    for call in fake_kr.calls:
        assert call["service"] not in ("Uoink", "Yoink"), (
            f"Isolated operation leaked access to ordinary service: {call}"
        )


@pytest.fixture(autouse=True)
def clean_key_env(monkeypatch):
    """Ensure no paid key environment variables exist during tests."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture
def fake_kr(monkeypatch):
    backend = RecordingFakeKeyring()
    monkeypatch.setattr(server, "_keyring", backend)
    monkeypatch.setattr(server, "_KEYRING_IMPORT_ERROR", None)
    return backend


def test_isolated_read(tmp_path, fake_kr):
    profile = tmp_path / "prof_read"
    profile.mkdir(parents=True)
    expected_svc = _expected_isolated_service(profile)
    fake_kr.passwords[(expected_svc, server.KEYRING_ANTHROPIC_USERNAME)] = "test-iso-key-1"

    with iso.bound_isolation(profile=profile, port=5180):
        val = server._get_saved_anthropic_key()

    assert val == "test-iso-key-1"
    assert_no_ordinary_service_calls(fake_kr)


def test_isolated_set(tmp_path, fake_kr):
    profile = tmp_path / "prof_set"
    profile.mkdir(parents=True)
    expected_svc = _expected_isolated_service(profile)

    with iso.bound_isolation(profile=profile, port=5180):
        server._store_saved_anthropic_key("test-iso-key-set")

    assert fake_kr.passwords.get((expected_svc, server.KEYRING_ANTHROPIC_USERNAME)) == "test-iso-key-set"
    assert_no_ordinary_service_calls(fake_kr)


def test_isolated_delete(tmp_path, fake_kr):
    profile = tmp_path / "prof_del"
    profile.mkdir(parents=True)
    expected_svc = _expected_isolated_service(profile)
    fake_kr.passwords[(expected_svc, server.KEYRING_ANTHROPIC_USERNAME)] = "test-iso-key-del"

    with iso.bound_isolation(profile=profile, port=5180):
        server._store_saved_anthropic_key("")

    assert (expected_svc, server.KEYRING_ANTHROPIC_USERNAME) not in fake_kr.passwords
    assert_no_ordinary_service_calls(fake_kr)


def test_absent_key_no_fallback(tmp_path, fake_kr):
    profile = tmp_path / "prof_absent"
    profile.mkdir(parents=True)
    # Seed ordinary and legacy stores with dummy keys
    fake_kr.passwords[("Uoink", server.KEYRING_ANTHROPIC_USERNAME)] = "ordinary-key"
    fake_kr.passwords[("Yoink", server.KEYRING_ANTHROPIC_USERNAME)] = "legacy-key"

    with iso.bound_isolation(profile=profile, port=5180):
        val = server._get_saved_anthropic_key()

    assert val == ""
    assert_no_ordinary_service_calls(fake_kr)


def test_profile_separation_same_port(tmp_path, fake_kr):
    profile_a = tmp_path / "prof_a"
    profile_b = tmp_path / "prof_b"
    profile_a.mkdir(parents=True)
    profile_b.mkdir(parents=True)
    shared_port = 5180

    with iso.bound_isolation(profile=profile_a, port=shared_port):
        server._store_saved_anthropic_key("key-for-profile-a")
        assert_no_ordinary_service_calls(fake_kr)

    with iso.bound_isolation(profile=profile_b, port=shared_port):
        assert server._get_saved_anthropic_key() == ""
        server._store_saved_anthropic_key("key-for-profile-b")
        assert_no_ordinary_service_calls(fake_kr)

    with iso.bound_isolation(profile=profile_a, port=shared_port):
        assert server._get_saved_anthropic_key() == "key-for-profile-a"
        assert_no_ordinary_service_calls(fake_kr)

    with iso.bound_isolation(profile=profile_b, port=shared_port):
        assert server._get_saved_anthropic_key() == "key-for-profile-b"
        assert_no_ordinary_service_calls(fake_kr)


def test_stable_profile_identity_different_ports(tmp_path, fake_kr):
    profile = tmp_path / "prof_stable"
    profile.mkdir(parents=True)

    with iso.bound_isolation(profile=profile, port=5180):
        server._store_saved_anthropic_key("key-stable-profile")
        assert_no_ordinary_service_calls(fake_kr)

    # Re-bind the exact same profile on a different port (e.g. 5182)
    with iso.bound_isolation(profile=profile, port=5182):
        assert server._get_saved_anthropic_key() == "key-stable-profile"
        assert_no_ordinary_service_calls(fake_kr)


def test_ordinary_legacy_compatibility(fake_kr):
    assert iso.current_binding() is None

    # Fallback to Yoink when Uoink key absent
    fake_kr.passwords[("Yoink", server.KEYRING_ANTHROPIC_USERNAME)] = "legacy-uoink-key"
    assert server._get_saved_anthropic_key() == "legacy-uoink-key"

    # Uoink key takes precedence when present
    fake_kr.passwords[("Uoink", server.KEYRING_ANTHROPIC_USERNAME)] = "modern-uoink-key"
    assert server._get_saved_anthropic_key() == "modern-uoink-key"

    # Set updates ordinary Uoink
    server._store_saved_anthropic_key("modern-uoink-updated")
    assert fake_kr.passwords[("Uoink", server.KEYRING_ANTHROPIC_USERNAME)] == "modern-uoink-updated"

    # Delete clears ordinary Uoink
    server._store_saved_anthropic_key("")
    assert ("Uoink", server.KEYRING_ANTHROPIC_USERNAME) not in fake_kr.passwords


def test_isolated_reset_401_path(tmp_path, fake_kr):
    profile = tmp_path / "prof_reset"
    profile.mkdir(parents=True)
    expected_svc = _expected_isolated_service(profile)
    fake_kr.passwords[(expected_svc, server.KEYRING_ANTHROPIC_USERNAME)] = "key-to-invalidate"
    fake_kr.passwords[("Uoink", server.KEYRING_ANTHROPIC_USERNAME)] = "keep-ordinary-intact"

    with iso.bound_isolation(profile=profile, port=5180):
        server._mark_anthropic_key_invalid()
        assert_no_ordinary_service_calls(fake_kr)

    assert (expected_svc, server.KEYRING_ANTHROPIC_USERNAME) not in fake_kr.passwords
    assert fake_kr.passwords[("Uoink", server.KEYRING_ANTHROPIC_USERNAME)] == "keep-ordinary-intact"


def test_isolated_public_settings(tmp_path, fake_kr):
    profile = tmp_path / "prof_settings"
    profile.mkdir(parents=True)

    with iso.bound_isolation(profile=profile, port=5180):
        public = server._public_settings({})
        assert public["anthropic_key_set"] is False
        assert public["anthropic_key_masked"] is None
        assert_no_ordinary_service_calls(fake_kr)

        server._store_saved_anthropic_key("sk-ant-testkey01-xyz9876")
        public2 = server._public_settings({})
        assert public2["anthropic_key_set"] is True
        assert public2["anthropic_key_masked"] == "sk-ant…9876"
        assert_no_ordinary_service_calls(fake_kr)


def test_isolated_plaintext_migration(tmp_path, fake_kr):
    profile = tmp_path / "prof_migrate"
    profile.mkdir(parents=True)
    settings_file = profile / "settings.json"
    settings_file.write_text(json.dumps({"anthropic_key": "sk-ant-plaintext-val"}), encoding="utf-8")
    expected_svc = _expected_isolated_service(profile)
    fake_kr.passwords[("Uoink", server.KEYRING_ANTHROPIC_USERNAME)] = "ordinary-untouched"

    with iso.bound_isolation(profile=profile, port=5180):
        server._migrate_plaintext_anthropic_key()
        assert_no_ordinary_service_calls(fake_kr)

    assert fake_kr.passwords.get((expected_svc, server.KEYRING_ANTHROPIC_USERNAME)) == "sk-ant-plaintext-val"
    assert fake_kr.passwords[("Uoink", server.KEYRING_ANTHROPIC_USERNAME)] == "ordinary-untouched"
    data = json.loads(settings_file.read_text(encoding="utf-8"))
    assert "anthropic_key" not in data
