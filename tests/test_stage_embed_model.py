"""Build staging of the bundled text-embedding model (3.18) fails closed.

Same stager and discipline as the Whisper model. A fake opener serves bytes,
so nothing is downloaded. The committed pin is checked against the notices,
the Windows installer, the macOS bundle build and local_embed's layout.
"""
from __future__ import annotations

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
import stage_embed_model as stager  # noqa: E402

FILES = {
    "config.json": b'{"synthetic": true}',
    "model.safetensors": b"\x08\x00\x00\x00\x00\x00\x00\x00{}      synthetic",
    "tokenizer.json": b'{"model": {}}',
}


def make_pin(files=FILES) -> dict:
    return {
        "schema_version": 1, "model": "potion-base-8m", "repo": "minishlab/potion-base-8M",
        "revision": "e" * 40, "license": "MIT",
        "files": {name: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                  for name, data in files.items()},
    }


class Opener:
    def __init__(self, served=None):
        self.served = dict(FILES if served is None else served)
        self.urls = []

    def __call__(self, url, timeout=None):
        self.urls.append(url)
        return io.BytesIO(self.served[url.rsplit("/", 1)[1]])


def test_stage_writes_the_layout_local_embed_reads(tmp_path):
    import local_embed
    opener = Opener()
    dest = stager.stage(make_pin(), tmp_path / "cache", tmp_path / "models" / "embed-bundled",
                        opener=opener, log=lambda _m: None)
    assert dest == tmp_path / "models" / local_embed.BUNDLED_DIRNAME / local_embed.MODEL_NAME
    assert sorted(opener.urls) == sorted(
        f"https://huggingface.co/minishlab/potion-base-8M/resolve/{'e' * 40}/{name}" for name in FILES)
    assert {p.name for p in dest.iterdir()} == set(FILES) | {"uoink-model.json"}
    manifest = json.loads((dest / "uoink-model.json").read_text(encoding="utf-8"))
    assert manifest["files"] == make_pin()["files"]


def test_hash_mismatch_fails_closed_and_names_the_embedding_model(tmp_path):
    tampered = {**FILES, "model.safetensors": FILES["model.safetensors"][:-1] + b"X"}
    with pytest.raises(stager.StageError, match="Embedding model hash mismatch.*model.safetensors"):
        stager.stage(make_pin(), tmp_path / "cache", tmp_path / "dest", opener=Opener(tampered),
                     log=lambda _m: None)
    assert not (tmp_path / "dest").exists()


def test_a_pin_without_the_weights_is_rejected(tmp_path):
    pin = make_pin()
    pin["files"].pop("model.safetensors")
    path = tmp_path / "pin.json"
    path.write_text(json.dumps(pin), encoding="utf-8")
    with pytest.raises(stager.StageError, match="must list model.safetensors"):
        stager.load_pin(path)


def test_cli_exits_nonzero_on_mismatch(tmp_path, capsys):
    pin = make_pin()
    pin["files"]["tokenizer.json"]["sha256"] = "0" * 64
    pin_path = tmp_path / "pin.json"
    pin_path.write_text(json.dumps(pin), encoding="utf-8")
    cache = stager.base.cache_dir_for(pin, tmp_path / "cache")
    cache.mkdir(parents=True)
    for name, data in FILES.items():
        (cache / name).write_bytes(data)
    assert stager.main(["--cache", str(tmp_path / "cache"), "--dest", str(tmp_path / "d"),
                        "--pin", str(pin_path)]) == 1
    assert "Embedding model hash mismatch" in capsys.readouterr().err


# ---- the committed pin and everything that depends on it --------------------------

def test_committed_pin_is_pinned_to_a_commit_and_matches_local_embed():
    import local_embed
    pin = stager.load_pin()
    assert pin["repo"] == "minishlab/potion-base-8M" and pin["license"] == "MIT"
    assert pin["model"] == local_embed.MODEL_NAME
    assert re.fullmatch(r"[0-9a-f]{40}", pin["revision"])
    assert set(pin["files"]) == {"config.json", "model.safetensors", "tokenizer.json"}
    assert pin["files"]["model.safetensors"]["size"] > 20_000_000


def test_notices_carry_the_pin():
    pin = stager.load_pin()
    spec = importlib.util.spec_from_file_location("notice_gen", ROOT / "scripts/gen_third_party_notices.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    committed = (ROOT / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")
    assert committed.count(generator.embed_model_block()) == 1
    notice = (ROOT / "third-party-notices/potion-base-8m-NOTICE.md").read_text(encoding="utf-8")
    assert pin["revision"] in notice and "Copyright (c) 2024 Thomas van Dongen" in notice
    for meta in pin["files"].values():
        assert meta["sha256"] in notice
    assert "](potion-base-8m-NOTICE.md)" in (ROOT / "third-party-notices/README.md").read_text(encoding="utf-8")


def test_windows_build_stages_installs_and_checks_the_model():
    build = (ROOT / "build.ps1").read_text(encoding="utf-8")
    source_only_return = build.index('if ($StageSourceOnly) {\n    Write-Host "Source staging complete')
    stage_call = build.index("scripts\\stage_embed_model.py")
    assert source_only_return < stage_call < build.index("Write-Step 'Staged smoke'")
    assert "(Join-Path $CacheDir 'embed-model')" in build
    assert "(Join-Path $StagingDir 'models\\embed-bundled')" in build
    assert "'third-party-notices\\potion-base-8m-NOTICE.md'" in build
    assert "import local_embed" in build.split("Write-Step 'Staged smoke'", 1)[1]
    for text in (build, (ROOT / "installer/verify_install.ps1").read_text(encoding="utf-8")):
        assert "'local_embed.py'" in text
    iss = (ROOT / "installer/uoink.iss").read_text(encoding="utf-8")
    assert 'Source: "staging\\local_embed.py"; DestDir: "{app}"' in iss
    assert ('Source: "staging\\models\\embed-bundled\\*"; DestDir: "{app}\\models\\embed-bundled"; '
            'Flags: recursesubdirs ignoreversion createallsubdirs') in iss
    assert 'Source: "staging\\third-party-notices\\potion-base-8m-NOTICE.md"' in iss
    install_delete = iss.split("\n[InstallDelete]\n", 1)[1].split("\n[", 1)[0]
    assert 'Type: filesandordirs; Name: "{app}\\models\\embed-bundled"' in install_delete
    verify = (ROOT / "installer/verify_install.ps1").read_text(encoding="utf-8")
    assert "'models\\embed-bundled\\potion-base-8m\\model.safetensors'" in verify


def test_mac_bundle_stages_the_same_pin_under_resources(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "scripts" / "mac"))
    import build_bundle
    assert build_bundle.EMBED_BUNDLE == Path("Contents/Resources/models/embed-bundled")
    assert "local_embed.py" in json.loads((ROOT / "scripts/mac/payload.json").read_text(encoding="utf-8"))["files"]
    pin = make_pin()
    monkeypatch.setattr(build_bundle.stage_embed_model, "load_pin", lambda: pin)
    cache = tmp_path / "cache"
    stager.base.fetch(pin, cache, opener=Opener(), log=lambda _m: None)  # pre-filled: no network
    evidence = build_bundle.stage_embed(tmp_path / "Uoink.app", cache)
    assert evidence["path"] == "Contents/Resources/models/embed-bundled/potion-base-8m"
    workflow = (ROOT / ".github/workflows/mac-qualify.yml").read_text(encoding="utf-8")
    assert "key: embed-model-${{ hashFiles('scripts/embed_model_pin.json') }}" in workflow
    assert '--embed-cache "$RUNNER_TEMP/embed-model"' in workflow
