"""Build staging of the bundled Whisper model fails closed.

A fake opener serves bytes, so no network and no Hugging Face cache. The
committed pin is checked for shape and for agreement with the notices, the
Windows installer and the macOS bundle build.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import stage_whisper_model as stager  # noqa: E402

FILES = {
    "config.json": b'{"synthetic": true}',
    "model.bin": b"\x06\x00\x00\x00synthetic weights",
    "tokenizer.json": b'{"tokens": []}',
    "vocabulary.txt": b"a\nb\nc\n",
}


def make_pin(files=FILES) -> dict:
    return {
        "schema_version": 1, "model": "base", "repo": "Systran/faster-whisper-base",
        "revision": "f" * 40, "license": "MIT",
        "files": {name: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                  for name, data in files.items()},
    }


class Opener:
    """urlopen stand-in that serves FILES (or overrides) and counts requests."""

    def __init__(self, served=None):
        self.served = dict(FILES if served is None else served)
        self.urls = []

    def __call__(self, url, timeout=None):
        self.urls.append(url)
        name = url.rsplit("/", 1)[1]
        return io.BytesIO(self.served[name])


def test_stage_fetches_the_pinned_revision_verifies_and_writes_manifest(tmp_path):
    pin, opener = make_pin(), Opener()
    dest = stager.stage(pin, tmp_path / "cache", tmp_path / "staging" / "models" / "whisper-bundled",
                        opener=opener, log=lambda _m: None)
    assert dest == tmp_path / "staging" / "models" / "whisper-bundled" / "base"
    assert sorted(opener.urls) == sorted(
        f"https://huggingface.co/Systran/faster-whisper-base/resolve/{'f' * 40}/{name}" for name in FILES)
    for name, data in FILES.items():
        assert (dest / name).read_bytes() == data
    manifest = json.loads((dest / stager.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["revision"] == "f" * 40 and manifest["files"] == pin["files"]
    assert {p.name for p in dest.iterdir()} == set(FILES) | {stager.MANIFEST_NAME}


def test_rebuild_reuses_the_cache_without_refetching(tmp_path):
    pin = make_pin()
    stager.stage(pin, tmp_path / "cache", tmp_path / "one", opener=Opener(), log=lambda _m: None)
    second = Opener()
    stager.stage(pin, tmp_path / "cache", tmp_path / "two", opener=second, log=lambda _m: None)
    assert second.urls == []
    assert (tmp_path / "two" / "base" / "model.bin").read_bytes() == FILES["model.bin"]


def test_hash_mismatch_fails_closed_and_drops_the_bad_download(tmp_path):
    tampered = {**FILES, "model.bin": b"\x06\x00\x00\x00synthetic weightz"}  # same size, other bytes
    cache = tmp_path / "cache"
    with pytest.raises(stager.StageError, match="hash mismatch.*model.bin: sha256"):
        stager.stage(make_pin(), cache, tmp_path / "dest", opener=Opener(tampered), log=lambda _m: None)
    assert not (stager.cache_dir_for(make_pin(), cache) / "model.bin").exists()
    assert not (tmp_path / "dest").exists(), "nothing may be staged after a mismatch"


def test_size_mismatch_fails_closed(tmp_path):
    short = {**FILES, "tokenizer.json": b"{}"}
    with pytest.raises(stager.StageError, match="tokenizer.json: size"):
        stager.stage(make_pin(), tmp_path / "cache", tmp_path / "dest", opener=Opener(short),
                     log=lambda _m: None)


def test_tampered_cache_file_fails_closed_then_refetches_on_rerun(tmp_path):
    pin, cache = make_pin(), tmp_path / "cache"
    stager.fetch(pin, cache, opener=Opener(), log=lambda _m: None)
    cached = stager.cache_dir_for(pin, cache) / "config.json"
    cached.write_bytes(b'{"synthetic": fals}')  # same length, different bytes
    with pytest.raises(stager.StageError, match="config.json"):
        stager.stage(pin, cache, tmp_path / "dest", opener=Opener(), log=lambda _m: None)
    assert not cached.exists()
    rerun = Opener()
    stager.stage(pin, cache, tmp_path / "dest2", opener=rerun, log=lambda _m: None)
    assert [url.rsplit("/", 1)[1] for url in rerun.urls] == ["config.json"]


def test_existing_staging_target_is_refused(tmp_path):
    (tmp_path / "dest" / "base").mkdir(parents=True)
    with pytest.raises(stager.StageError, match="already exists"):
        stager.stage(make_pin(), tmp_path / "cache", tmp_path / "dest", opener=Opener(), log=lambda _m: None)


def test_cli_exits_nonzero_on_mismatch(tmp_path, monkeypatch, capsys):
    pin_path = tmp_path / "pin.json"
    pin = make_pin()
    pin["files"]["model.bin"]["sha256"] = "0" * 64
    pin_path.write_text(json.dumps(pin), encoding="utf-8")
    cache = stager.cache_dir_for(pin, tmp_path / "cache")
    cache.mkdir(parents=True)
    for name, data in FILES.items():
        (cache / name).write_bytes(data)  # cached, so the CLI never reaches the network
    code = stager.main(["--cache", str(tmp_path / "cache"), "--dest", str(tmp_path / "dest"),
                        "--pin", str(pin_path)])
    assert code == 1
    assert "hash mismatch" in capsys.readouterr().err


@pytest.mark.parametrize("mutate,message", [
    (lambda p: p.update(revision="main"), "full 40-character commit"),
    (lambda p: p["files"].pop("tokenizer.json"), "must list"),
    (lambda p: p["files"].update({"../model.bin": {"size": 1, "sha256": "0" * 64}}), "Invalid pinned file name"),
    (lambda p: p["files"]["model.bin"].update(sha256="ABC"), "lowercase sha256"),
    (lambda p: p.update(repo="not a repo"), "Invalid pinned repository"),
])
def test_ambiguous_pins_are_rejected(tmp_path, mutate, message):
    pin = copy.deepcopy(make_pin())
    mutate(pin)
    path = tmp_path / "pin.json"
    path.write_text(json.dumps(pin), encoding="utf-8")
    with pytest.raises(stager.StageError, match=message):
        stager.load_pin(path)


# ---- the committed pin and every place that depends on it ----------------------

def test_committed_pin_is_valid_and_pinned_to_a_commit():
    pin = stager.load_pin()
    assert pin["model"] == "base" and pin["repo"] == "Systran/faster-whisper-base"
    assert re.fullmatch(r"[0-9a-f]{40}", pin["revision"])
    assert set(pin["files"]) == {"config.json", "model.bin", "tokenizer.json", "vocabulary.txt"}


def test_notices_carry_the_pinned_revision_and_hashes():
    pin = stager.load_pin()
    spec = importlib.util.spec_from_file_location("notice_gen", ROOT / "scripts/gen_third_party_notices.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    committed = (ROOT / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")
    assert committed.count(generator.whisper_model_block()) == 1
    notice = (ROOT / "third-party-notices/faster-whisper-base-NOTICE.md").read_text(encoding="utf-8")
    assert pin["revision"] in notice and "Copyright (c) 2022 OpenAI" in notice
    for meta in pin["files"].values():
        assert meta["sha256"] in notice
    assert "](faster-whisper-base-NOTICE.md)" in (ROOT / "third-party-notices/README.md").read_text(encoding="utf-8")


def test_windows_build_stages_and_installs_the_model():
    build = (ROOT / "build.ps1").read_text(encoding="utf-8")  # universal newlines
    # Full builds only: source-only staging never downloads.
    source_only_return = build.index('if ($StageSourceOnly) {\n    Write-Host "Source staging complete')
    stage_call = build.index("scripts\\stage_whisper_model.py")
    assert source_only_return < stage_call < build.index("Write-Step 'Staged smoke'")
    assert "(Join-Path $CacheDir 'whisper-model')" in build
    assert "(Join-Path $StagingDir 'models\\whisper-bundled')" in build
    assert "throw 'Bundled Whisper model staging failed" in build
    assert "'third-party-notices\\faster-whisper-base-NOTICE.md'" in build
    iss = (ROOT / "installer/uoink.iss").read_text(encoding="utf-8")
    assert ('Source: "staging\\models\\whisper-bundled\\*"; DestDir: "{app}\\models\\whisper-bundled"; '
            'Flags: recursesubdirs ignoreversion createallsubdirs') in iss
    assert 'Source: "staging\\third-party-notices\\faster-whisper-base-NOTICE.md"' in iss
    install_delete = iss.split("\n[InstallDelete]\n", 1)[1].split("\n[", 1)[0]
    assert 'Type: filesandordirs; Name: "{app}\\models\\whisper-bundled"' in install_delete
    verify = (ROOT / "installer/verify_install.ps1").read_text(encoding="utf-8")
    assert "'models\\whisper-bundled\\base\\model.bin'" in verify


def test_mac_bundle_stages_the_same_pin_under_resources(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "scripts" / "mac"))
    import build_bundle
    assert build_bundle.WHISPER_BUNDLE == Path("Contents/Resources/models/whisper-bundled")
    pin = make_pin()
    monkeypatch.setattr(build_bundle.stage_whisper_model, "load_pin", lambda: pin)
    cache = tmp_path / "cache"
    stager.fetch(pin, cache, opener=Opener(), log=lambda _m: None)  # pre-filled: no network
    app = tmp_path / "Uoink.app"
    evidence = build_bundle.stage_whisper(app, cache)
    staged = app / "Contents/Resources/models/whisper-bundled/base"
    assert evidence["path"] == "Contents/Resources/models/whisper-bundled/base"
    assert evidence["revision"] == "f" * 40
    assert (staged / "model.bin").read_bytes() == FILES["model.bin"]
    # Code in a data folder would be signed as code: refuse it.
    macho = {**FILES, "model.bin": b"\xcf\xfa\xed\xfe" + b"x" * 12}
    pin = make_pin(macho)
    monkeypatch.setattr(build_bundle.stage_whisper_model, "load_pin", lambda: pin)
    other_cache = tmp_path / "other-cache"
    stager.fetch(pin, other_cache, opener=Opener(macho), log=lambda _m: None)
    with pytest.raises(ValueError, match="looks like code"):
        build_bundle.stage_whisper(tmp_path / "Other.app", other_cache)
    workflow = (ROOT / ".github/workflows/mac-qualify.yml").read_text(encoding="utf-8")
    assert "key: whisper-model-${{ hashFiles('scripts/whisper_model_pin.json') }}" in workflow
    assert '--whisper-cache "$RUNNER_TEMP/whisper-model"' in workflow
