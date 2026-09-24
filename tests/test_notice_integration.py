"""Notice behavior against copied text and injected package metadata only."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("focused_notice_generator", ROOT / "scripts/gen_third_party_notices.py")
notices = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notices)


def rows():
    return [{"Name": line.split("==")[0], "Version": line.split("==")[1], "License": "fixture-metadata"}
            for line in (ROOT / "requirements-installer-lock.txt").read_text().splitlines()
            if line and not line.startswith("#")]


def output_for(tmp_path, monkeypatch, data):
    target = tmp_path / "notices.md"
    monkeypatch.setattr(notices, "_from_pip_licenses", lambda: data)
    monkeypatch.setattr(notices.sys, "argv", ["notices", str(target)])
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "946684800")
    return target


@pytest.mark.parametrize("name", ["proxy_tools", "proxy-tools"])
def test_metadata_label_and_conflict_survive_normalized_name(tmp_path, monkeypatch, name):
    data = rows()
    row = next(row for row in data if row["Name"] == "proxy_tools")
    row["Name"] = name
    before = json.loads(json.dumps(data))
    target = output_for(tmp_path, monkeypatch, data)
    assert notices.main() == 0
    text = target.read_text(encoding="utf8")
    assert f"| {name} | 0.1.0 | fixture-metadata (metadata; see upstream conflict below) |" in text
    assert "historical setup.py say MIT" in text and "repository license say BSD" in text
    assert text.count("## Supplemental upstream notices") == 1
    assert text.count("third-party-notices/antlr4-python3-runtime-4.9.3-LICENSE.txt") == 1
    assert text.count("third-party-notices/proxy-tools-0.1.0-UPSTREAM-LICENSE.txt") == 1
    assert "2000-01-01" in text and data == before


def test_failed_pip_collectors_reach_injected_importlib_fallback(tmp_path, monkeypatch):
    data, calls = rows(), []
    target = tmp_path / "fallback.md"
    def failed(command, **kwargs):
        calls.append(command)
        raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(notices.subprocess, "check_output", failed)
    monkeypatch.setattr(notices, "_from_importlib", lambda: data)
    monkeypatch.setattr(notices.sys, "argv", ["notices", str(target)])
    assert notices.main() == 0
    assert [command[2] for command in calls] == ["piplicenses", "pip_licenses"]
    text = target.read_text(encoding="utf8")
    assert "source: importlib.metadata (pip-licenses unavailable)" in text
    assert notices.SUPPLEMENTAL_NOTICE_BLOCK in text


@pytest.mark.parametrize("name", ["proxy_tools", "antlr4-python3-runtime"])
def test_changed_version_refuses_without_overwriting_old_index(tmp_path, monkeypatch, name):
    data = rows()
    next(row for row in data if row["Name"] == name)["Version"] = "unreviewed-version"
    target = output_for(tmp_path, monkeypatch, data)
    old = b"Existing index must not be relabeled as freshly generated.\n"
    target.write_bytes(old)
    with pytest.raises(RuntimeError, match="Supplemental notice requires review"):
        notices.main()
    assert target.read_bytes() == old


def test_exact_upstream_bytes_and_relative_links():
    folder = ROOT / "third-party-notices"
    expected = {
        "antlr4-python3-runtime-4.9.3-LICENSE.txt": (2699, "b1b379fcaf3219593a4c433feb1b35c780bed23fafaae440b1ae2771a9521e3a"),
        "proxy-tools-0.1.0-UPSTREAM-LICENSE.txt": (1436, "a428fb8a2e762af3eb0a6edbbb88e9b42ccfee80fd9b423958bcacf9b9abbfe4"),
    }
    assert (folder / ".gitattributes").read_bytes() == b"* -text\n"
    for name, (size, digest) in expected.items():
        raw = (folder / name).read_bytes()
        assert (len(raw), hashlib.sha256(raw).hexdigest()) == (size, digest)
        assert f"third-party-notices/{name}" in notices.SUPPLEMENTAL_NOTICE_BLOCK
        assert f"]({name})" in (folder / "README.md").read_text(encoding="utf8")
    proxy = (folder / "proxy-tools-0.1.0-UPSTREAM-LICENSE.txt").read_text(encoding="utf8")
    assert "Copyright (c) 2013 Armin Ronacher" in proxy
    assert "Copyright (c) 2014 Jonathan Tushman" in proxy
    assert "<COPYRIGHT HOLDER>" in proxy and "DAMAGE.OTHERWISE," in proxy


def test_generated_and_committed_supplement_match():
    committed = (ROOT / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf8")
    assert committed.count(notices.SUPPLEMENTAL_NOTICE_BLOCK) == 1
    assert committed.count(notices.FFMPEG_BLOCK) == 1
    installer = (ROOT / "installer/uoink.iss").read_text(encoding="utf8")
    for name in ("README.md", "antlr4-python3-runtime-4.9.3-LICENSE.txt", "proxy-tools-0.1.0-UPSTREAM-LICENSE.txt"):
        assert f'Source: "staging\\third-party-notices\\{name}"; DestDir: "{{app}}\\third-party-notices"; Flags: ignoreversion' in installer
    assert 'Source: "staging\\THIRD-PARTY-NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion' in installer
