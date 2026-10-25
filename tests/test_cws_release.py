"""Store packaging and link switches; temporary files only, no helper or network."""
import importlib.util
import json
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
