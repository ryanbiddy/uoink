"""Store packaging and link switches; temporary files only, no helper or network."""
import importlib.util
import json
import re
from pathlib import Path
import shutil
import subprocess
import zipfile

import pytest
import uoink_store

ROOT = Path(__file__).resolve().parents[1]
ID = "abcdefghijklmnopabcdefghijklmnop"
URL = "https://chromewebstore.google.com/detail/uoink/" + ID


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def release(tmp_path):
    shutil.copytree(ROOT / "extension", tmp_path / "extension")
    shutil.copy(ROOT / "VERSION", tmp_path / "VERSION")
    shutil.copy(ROOT / "README.md", tmp_path / "README.md")
    (tmp_path / "docs/store").mkdir(parents=True)
    shutil.copy(ROOT / "docs/store/website-copy-notes.md", tmp_path / "docs/store/website-copy-notes.md")
    return tmp_path


def test_zip_is_reproducible_and_preserves_source_key(release):
    builder = script("build_cws")
    source = (release / "extension/manifest.json").read_bytes()
    archive = builder.build(release)
    first = archive.read_bytes()
    assert builder.build(release).read_bytes() == first
    with zipfile.ZipFile(archive) as z:
        assert z.namelist() == sorted(builder.ALLOWLIST)
        assert "key" not in json.loads(z.read("manifest.json"))
        assert json.loads(z.read("manifest.json"))["version"] == (release / "VERSION").read_text().strip()
        assert b"const USE_MOCK_API = false;" in z.read("lib/extract.js")
        assert not any("mock-api" in n or n.endswith(".map") for n in z.namelist())
    assert (release / "extension/manifest.json").read_bytes() == source


@pytest.mark.parametrize("name", ["debug.js", "popup.js.map", "private.pem", "lib/unreviewed.js"])
def test_zip_rejects_every_unlisted_file(release, name):
    (release / "extension" / name).write_text("not for release", encoding="utf-8")
    with pytest.raises(ValueError, match="allowlist mismatch"):
        script("build_cws").build(release)


def test_zip_rejects_mock_mode_and_version_drift(release):
    extract = release / "extension/lib/extract.js"
    original = extract.read_text(encoding="utf-8")
    extract.write_text(original.replace("const USE_MOCK_API = false;", "const USE_MOCK_API = true;"), encoding="utf-8")
    with pytest.raises(ValueError, match="USE_MOCK_API"):
        script("build_cws").build(release)
    extract.write_text(original, encoding="utf-8")
    (release / "VERSION").write_text("0.0.1", encoding="utf-8")
    with pytest.raises(ValueError, match="match VERSION"):
        script("build_cws").build(release)


@pytest.mark.parametrize("url", ["", URL])
def test_shared_config_drives_splash_and_generated_install_copy(release, monkeypatch, url):
    config_path = release / "extension/store-config.json"
    config_path.write_text(json.dumps({"chrome_web_store_id": ID, "chrome_web_store_url": url}), encoding="utf-8")
    monkeypatch.setattr(uoink_store, "CONFIG_PATH", config_path)
    import uoink_splash
    monkeypatch.setattr(uoink_splash, "_sentinel_path", lambda: release / "first-run")
    monkeypatch.setattr(uoink_splash, "_extension_sentinel_path", lambda: release / "extension-loaded")
    monkeypatch.setattr(uoink_splash, "_extension_dir", lambda: release / "extension")
    monkeypatch.setattr(uoink_splash, "_preferred_browser", lambda: {"id": "chrome"})
    monkeypatch.setattr(uoink_splash, "_available_browsers", lambda: [])
    assert uoink_splash.JsApi().extension_status()["store_url"] == url
    sync = script("sync_store_links")
    sync.sync(release)
    sync.sync(release, check=True)
    for path in (release / "README.md", release / "docs/store/website-copy-notes.md"):
        block = path.read_text(encoding="utf-8").split(sync.START)[1].split(sync.END)[0]
        assert (f"[Add to Chrome]({URL})" in block) is bool(url)
        assert "Load unpacked" in block
        if url:
            assert "Advanced" in block


@pytest.mark.parametrize("id,url", [
    ("*", ""), ("a" * 31, ""), (ID.upper(), ""), (ID + "/", ""),
    (ID, "https://evil.test/"), (ID, URL + ".evil.test"),
    (ID, URL + "?redirect=evil"), (ID, URL.replace("https:", "http:")),
    (ID, URL.replace(".com", ".com.evil.test")), ("", URL), (None, ""),
])
def test_bad_store_config_fails_closed(tmp_path, id, url):
    path = tmp_path / "store-config.json"
    path.write_text(json.dumps({"chrome_web_store_id": id, "chrome_web_store_url": url}), encoding="utf-8")
    assert uoink_store.load_store_config(path) == uoink_store.EMPTY_CONFIG
    with pytest.raises(ValueError):
        uoink_store.load_store_config(path, strict=True)


def test_store_ui_behaviour():
    result = subprocess.run(["node", "tests/js/cws_store_links_test.mjs"], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_zip_is_clean_named_for_version_and_receipt_matches(release):
    builder = script("build_cws")
    version = (release / "VERSION").read_text().strip()
    archive = builder.build(release)
    assert archive.name == f"uoink-extension-{version}-cws.zip"
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        manifest = json.loads(z.read("manifest.json"))
        source_key = json.loads((release / "extension/manifest.json").read_text())["key"]
        assert "key" not in manifest and source_key not in z.read("manifest.json").decode()
        assert manifest["version"] == version and manifest["manifest_version"] == 3
        assert not [n for n in names if builder.FORBIDDEN.search(n)], names
        assert not [n for n in names if re.search(r"(^|/)(tests?|mocks?)(/|$)|\.map$|\.pem$|\.md$", n)]
        assert "setup.html" in names and "setup.js" in names
        sizes = {i.filename: i.file_size for i in z.infolist()}
    receipt = json.loads(archive.with_suffix(".contents.json").read_text())
    assert receipt["version"] == version and receipt["bytes"] == archive.stat().st_size
    assert {f["path"]: f["bytes"] for f in receipt["files"]} == sizes
    lines = builder.report(archive)
    assert lines[0] == str(archive) and lines[1] == f"{archive.stat().st_size:,} bytes"
    assert len(lines) == 3 + len(names)


def test_build_refuses_a_forbidden_name_even_if_allowlisted(release, monkeypatch):
    builder = script("build_cws")
    monkeypatch.setattr(builder, "ALLOWLIST", builder.ALLOWLIST | {"lib/popup.test.js"})
    with pytest.raises(ValueError, match="test, mock"):
        builder.build(release)


def test_store_docs_name_one_version_that_is_not_older_than_version_file():
    def parse(v):
        return tuple(int(x) for x in v.split("."))
    current = parse((ROOT / "VERSION").read_text().strip())
    submit = (ROOT / "docs/store/SUBMIT-NOW.md").read_text(encoding="utf-8")
    found = set(re.findall(r"uoink-extension-(\d+\.\d+\.\d+)-cws\.zip", submit))
    found |= set(re.findall(r"Submit Uoink (\d+\.\d+\.\d+) to the Chrome Web Store", submit))
    found |= set(re.findall(r"detected name is \*\*Uoink\*\*, version \*\*(\d+\.\d+\.\d+)\*\*", submit))
    assert len(found) == 1, f"SUBMIT-NOW.md names more than one version: {sorted(found)}"
    # VERSION may still be the previous release before the owner bumps it for 3.17.0.
    assert parse(found.pop()) >= current, "SUBMIT-NOW.md is older than VERSION"
    for name in ("README.md", "SUBMISSION-CHECKLIST.md", "listing.md", "permissions-justification.md", "SCREENSHOTS.md"):
        text = (ROOT / "docs/store" / name).read_text(encoding="utf-8")
        first = text.splitlines()[0]
        assert "3.12 " not in first and "3.11 " not in first, name


def test_every_manifest_permission_is_justified_for_the_store():
    manifest = json.loads((ROOT / "extension/manifest.json").read_text(encoding="utf-8"))
    text = (ROOT / "docs/store/permissions-justification.md").read_text(encoding="utf-8")
    headings = set(re.findall(r"^## (\w+)$", text, re.M))
    missing = [p for p in manifest["permissions"] if p not in headings]
    assert not missing, f"permissions-justification.md has no section for {missing}"
    for host in manifest["host_permissions"]:
        assert host in text or host.replace("https://*.", "https://*.") in text, host


def test_store_screenshots_are_1280x800_and_listed():
    import struct
    shots = sorted((ROOT / "docs/store/screenshots").glob("*.png"))
    listing = (ROOT / "docs/store/SCREENSHOTS.md").read_text(encoding="utf-8")
    assert len(shots) >= 5
    for path in shots:
        data = path.read_bytes()
        assert data[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10]), path.name
        assert struct.unpack(">II", data[16:24]) == (1280, 800), path.name
        assert path.name in listing, f"{path.name} is not described in SCREENSHOTS.md"
