"""Offline tests of the pinned recipe, extraction boundary and Darwin media gate."""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from types import SimpleNamespace

import pytest

import _platform

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/mac"))
import build_ffmpeg as ff
import ffmpeg_bundle


def test_verified_source_pins_and_build_policy():
    config = ff.load_config()
    for role, size, digest in (
        ("cli", 11710924, "464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c"),
        ("shared", 11050340, "de668509caf9e35e3cd162473441fdb29538c6d96ed080292b3cf9e6fc5d558f"),
    ):
        assert config[role]["size_bytes"] == size
        assert config[role]["sha256"] == digest
        assert config[role]["signing_key_fingerprint"] == ff.FINGERPRINT
        flags = ff.configure_flags(config, role)
        assert {"--disable-autodetect", "--disable-gpl", "--disable-nonfree"} <= set(flags)
        assert "av1" not in ff.components(config, role)["decoder"]
        assert "mp3" not in ff.components(config, role).get("encoder", [])
    assert "--enable-network" in ff.configure_flags(config, "cli")
    assert "--enable-network" not in ff.configure_flags(config, "shared")
    assert "--disable-network" not in ff.configure_flags(config, "cli")
    assert "--disable-network" in ff.configure_flags(config, "shared")
    assert "--disable-version3" not in config["common_flags"]
    assert set(ff.components(config, "cli")["protocol"]) == {
        "file", "pipe", "http", "https", "tcp", "tls", "crypto"}
    # These endpoints are built into libavfilter, not configurable filters.
    assert not {"buffer", "buffersink", "abuffer", "abuffersink"} & set(config["components"]["filter"])
    original = ff.cache_key(config)
    for change in ("hash", "flags"):
        changed = copy.deepcopy(config)
        if change == "hash":
            changed["cli"]["sha256"] = "0" * 64
        else:
            changed["cli"]["components"]["filter"].append("select")
        assert ff.cache_key(changed) != original


@pytest.mark.parametrize("field,value", [
    ("url", "https://example.test/source.tar.xz"), ("size_bytes", True),
    ("sha256", "bad"), ("signing_key_fingerprint", "0" * 40),
    ("flags", ["--enable-gpl"]), ("version", "latest"),
])
def test_payload_validation_fails_closed(tmp_path, field, value):
    manifest = json.loads((ROOT / "scripts/mac/payload.json").read_text())
    manifest["ffmpeg"]["cli"][field] = value
    path = tmp_path / "payload.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        ff.load_config(path)


def test_archive_checks_bytes_before_open_or_extract(monkeypatch, tmp_path):
    archive = tmp_path / "ffmpeg.tar.xz"
    archive.write_bytes(b"not an archive")
    pin = {"version": "8.1.2", "size_bytes": archive.stat().st_size, "sha256": ff.digest(archive)}
    monkeypatch.setattr(ff.tarfile, "open", lambda *args, **kwargs: pytest.fail("Opened unchecked archive"))
    for bad in ({**pin, "size_bytes": 1}, {**pin, "sha256": "0" * 64}):
        with pytest.raises(ValueError, match="size/hash"):
            ff.extract_source(archive, tmp_path / "out", bad)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("name,ok", [("ffmpeg-8.1.2/configure", True),
    ("ffmpeg-8.1.2/../../outside", False), ("wrong/configure", False)])
def test_source_archive_root_and_traversal(tmp_path, name, ok):
    path = tmp_path / "source.tar.xz"
    with tarfile.open(path, "w:xz") as archive:
        entry = tarfile.TarInfo(name)
        entry.size = 5
        archive.addfile(entry, io.BytesIO(b"hello"))
    pin = {"version": "8.1.2", "size_bytes": path.stat().st_size, "sha256": ff.digest(path)}
    if ok:
        assert (ff.extract_source(path, tmp_path / "out", pin) / "configure").read_bytes() == b"hello"
    else:
        with pytest.raises((ValueError, tarfile.FilterError)):
            ff.extract_source(path, tmp_path / "out", pin)
    assert not (tmp_path / "outside").exists()


def test_cached_output_is_reverified(tmp_path):
    config = ff.load_config()
    file = tmp_path / "ffmpeg"
    file.write_bytes(b"built")
    ff.write_json(tmp_path / "cache.json", {"key": ff.cache_key(config), "files": ff.output_inventory(tmp_path)})
    ff.verify_output(tmp_path, config)
    file.write_bytes(b"modified")
    with pytest.raises(ValueError, match="hash"):
        ff.verify_output(tmp_path, config)


@pytest.mark.parametrize("role", ["cli", "shared"])
def test_configure_success_cannot_hide_missing_components_or_gpl(role):
    config = ff.load_config()
    # A successful configure with missing native codecs must still fail closed.
    with pytest.raises(ValueError, match="CONFIG_H264_DECODER"):
        ff.validate_configuration(config, role, "#define CONFIG_ZLIB 1\n")
    macros = {f"CONFIG_{name.upper()}_{kind.upper()}"
              for kind, names in ff.components(config, role).items() for name in names}
    macros.update(f"CONFIG_{name.upper()}" for name in ff.LIBRARIES)
    macros.add("CONFIG_ZLIB")
    macros.update({"CONFIG_STATIC", "CONFIG_FFMPEG", "CONFIG_FFPROBE", "CONFIG_NETWORK", "CONFIG_SECURETRANSPORT"}
                  if role == "cli" else {"CONFIG_SHARED"})
    headers = "".join(f"#define {name} 1\n" for name in sorted(macros))
    ff.validate_configuration(config, role, headers)
    with pytest.raises(ValueError, match="forbidden=.*CONFIG_GPL"):
        ff.validate_configuration(config, role, headers + "#define CONFIG_GPL 1\n")


def test_build_cannot_download_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(ff, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(ff.urllib.request, "urlopen", lambda *args, **kwargs: pytest.fail("network"))
    with pytest.raises(RuntimeError, match="native macOS arm64"):
        ff.build(tmp_path / "output")
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("role", ["cli", "shared"])
def test_every_requested_component_is_checked_against_pinned_source(monkeypatch, tmp_path, role):
    config = ff.load_config()
    requested = ff.components(config, role)
    seen = []

    def run(command, **kwargs):
        kind = command[-1].removeprefix("--list-").removesuffix("s")
        seen.append(kind)
        assert command[:2] == ["/bin/bash", tmp_path / "configure"]
        return SimpleNamespace(stdout="\n".join(requested[kind]))

    monkeypatch.setattr(ff, "run", run)
    assert ff.validate_source_components(config, role, tmp_path, {}) == requested
    assert set(seen) == set(requested)
    monkeypatch.setattr(ff, "run", lambda *args, **kwargs: SimpleNamespace(stdout=""))
    with pytest.raises(ValueError, match="unknown"):
        ff.validate_source_components(config, role, tmp_path, {})


@pytest.mark.parametrize("phase", ["configure", "make", "install"])
def test_build_failures_print_both_log_tails_and_preserve_error(monkeypatch, tmp_path, capsys, phase):
    source, evidence = tmp_path / "source", tmp_path / "evidence"
    (source / "ffbuild").mkdir(parents=True)
    evidence.mkdir()
    (source / "ffbuild/config.log").write_text("".join(f"config-{i}\n" for i in range(170)))
    for name in ("config.h", "config_components.h"):
        (source / name).touch()
    monkeypatch.setattr(ff, "validate_source_components", lambda *args: {})
    monkeypatch.setattr(ff, "validate_configuration", lambda *args: None)
    error = subprocess.CalledProcessError(17, [phase])
    calls = []

    def run(command, **kwargs):
        step = "configure" if command[0] == "configure" else "install" if command[-1] == "install" else "make"
        calls.append(step)
        if step == phase:
            kwargs["stdout"].write("".join(f"build-{i}\n" for i in range(170)))
            raise error

    monkeypatch.setattr(ff, "run", run)
    with pytest.raises(subprocess.CalledProcessError) as exc:
        ff.configure_and_build(ff.load_config(), "cli", source, evidence, ["configure"], {})
    assert exc.value is error
    output = capsys.readouterr().err
    for label in ("config", "build"):
        assert f"{label}-19\n" not in output
        assert f"{label}-20\n" in output and f"{label}-169\n" in output
    assert (evidence / "config.log").read_text() == (source / "ffbuild/config.log").read_text()
    assert calls[-1] == phase


def test_darwin_dev_mode_uses_resolvable_path_ffmpeg(monkeypatch, tmp_path):
    binary = tmp_path / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    binary.touch(mode=0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform="darwin",
        executable=str(tmp_path / "dev-python")))
    # A module copied into Resources alone does not make the interpreter bundled.
    monkeypatch.setattr(_platform, "__file__", str(tmp_path / "Uoink.app/Contents/Resources/_platform.py"))
    monkeypatch.setattr(_platform.subprocess, "run", lambda *a, **k: pytest.fail("dev self-test"))
    assert Path(shutil.which(_platform.media_binary("ffmpeg"))) == binary
    assert _platform.mac_bundle_contents() is None
    assert _platform.media_capability()["available"] is True
    assert _platform.alignment_capability()["available"] is True
    _platform.require_media()
    assert _platform.ytdlp_media_args() == []
    assert _platform.video_format("original") == "original"
    assert _platform.podcast_audio_format() == "mp3"


@pytest.fixture
def darwin_bundle(monkeypatch, tmp_path):
    contents = tmp_path / "Relocated With Spaces/Uoink.app/Contents"
    (contents / "Helpers").mkdir(parents=True)
    (contents / "Resources").mkdir()
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform="darwin",
        executable=str(contents / "Resources/Python/bin/python3")))
    monkeypatch.setattr(_platform, "__file__", str(contents / "Resources/_platform.py"))
    monkeypatch.setenv("PATH", "/opt/homebrew/bin")
    _platform._media_self_test.cache_clear()
    yield contents
    _platform._media_self_test.cache_clear()


def test_missing_binary_never_falls_back_to_path(darwin_bundle, monkeypatch):
    monkeypatch.setattr(_platform.subprocess, "run", lambda *a, **k: pytest.fail("PATH executable"))
    with pytest.raises(FileNotFoundError):
        _platform.media_binary("ffmpeg")
    assert _platform.media_capability()["code"] == "media_requires_ffmpeg"
    assert _platform.ytdlp_media_args() == ["--ignore-config", "--ffmpeg-location", str(darwin_bundle / "Helpers")]
    with pytest.raises(_platform.MediaUnavailableError, match="media_requires_ffmpeg"):
        _platform.require_media()


def test_bundle_policy_cannot_be_relaxed_by_environment_or_module_path(darwin_bundle, monkeypatch, tmp_path):
    monkeypatch.setattr(_platform, "__file__", str(tmp_path / "source/_platform.py"))
    monkeypatch.setenv("UOINK_DEV_MODE", "1")
    monkeypatch.setenv("UOINK_BUNDLE_MODE", "0")
    assert _platform.mac_bundle_contents() == darwin_bundle
    assert _platform.media_capability()["code"] == "media_requires_ffmpeg"


def test_renamed_app_still_requires_bundled_media(monkeypatch, tmp_path):
    contents = tmp_path / "Renamed by user.app/Contents"
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform="darwin",
        executable=str(contents / "Resources/Python/bin/python3")))
    assert _platform.mac_bundle_contents() == contents
    assert _platform.media_capability()["code"] == "media_requires_ffmpeg"


@pytest.mark.parametrize("relative", [
    "Resources/Python/bin/python3", "Resources/Python/bin/python3.13",
    "Resources/Python/bin/pip3", "Resources/Python/lib/python3.13/tool",
    "Frameworks/Python/bin/python3", "MacOS/Uoink", "Resources/python/bin/python3",
])
def test_bundle_detection_requires_exact_embedded_interpreter(monkeypatch, tmp_path, relative):
    contents = tmp_path / "Relocated Name.app/Contents"
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform="darwin", executable=str(contents / relative)))
    monkeypatch.setenv("UOINK_BUNDLE_MODE", "1")
    monkeypatch.setattr(_platform, "__file__", str(contents / "Resources/_platform.py"))
    expected = contents if relative == "Resources/Python/bin/python3" else None
    assert _platform.mac_bundle_contents() == expected


@pytest.mark.parametrize("external", [False, True])
def test_bundle_detection_uses_real_location_and_canonical_python_link(monkeypatch, tmp_path, external):
    contents = tmp_path / "Uoink.app/Contents"
    python = contents / "Resources/Python/bin/python3"
    python.parent.mkdir(parents=True)
    target = tmp_path / "external-python" if external else python.with_name("python3.13")
    target.touch()
    alias = tmp_path / "python-alias"
    try:
        python.symlink_to(target)
        alias.symlink_to(python)
    except OSError as error:
        pytest.skip(f"Symlink creation unavailable: {error}")
    for launch in (python, target, alias):
        monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform="darwin", executable=str(launch)))
        assert _platform.mac_bundle_contents() == (None if external else contents)


@pytest.mark.parametrize("external", [False, True])
def test_bundle_detection_resolved_links_without_os_symlink_privilege(monkeypatch, tmp_path, external):
    contents = tmp_path / "Uoink.app/Contents"
    python = contents / "Resources/Python/bin/python3"
    target = tmp_path / "external-python" if external else python.with_name("python3.13")
    alias = tmp_path / "alias"
    resolve = Path.resolve
    monkeypatch.setattr(Path, "resolve", lambda path, **kw: target if path in (alias, python) else resolve(path, **kw))
    for launch in (python, alias, target):
        monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform="darwin", executable=str(launch)))
        assert _platform.mac_bundle_contents() == (None if external else contents)


@pytest.mark.parametrize("failure", [None, "version", "decode", "empty", "silence"])
def test_capability_requires_version_and_generated_decode(darwin_bundle, monkeypatch, failure):
    for name in ("ffmpeg", "ffprobe"):
        (darwin_bundle / "Helpers" / name).write_bytes(b"binary")
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert Path(command[0]).parent == darwin_bundle / "Helpers"
        if (failure == "version" and command[-1] == "-version") or (failure == "decode" and "-i" in command):
            raise subprocess.CalledProcessError(1, command)
        if "-i" in command:
            assert kwargs["input"].startswith(b"RIFF")
            return SimpleNamespace(stdout=b"" if failure == "empty" else b"\0" * 3200 if failure == "silence" else b"\x10\0" * 1600)
        return SimpleNamespace(stdout=b"version")

    monkeypatch.setattr(_platform.subprocess, "run", run)
    assert _platform.media_capability()["available"] is (failure is None)
    previous = len(calls)
    _platform.media_capability()
    assert len(calls) == previous
    (darwin_bundle / "Helpers/ffmpeg").unlink()
    assert _platform.media_capability()["code"] == "media_requires_ffmpeg"


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_other_platforms_keep_commands_and_formats(monkeypatch, platform):
    monkeypatch.setattr(_platform, "sys", SimpleNamespace(platform=platform))
    assert _platform.media_binary("ffmpeg") == "ffmpeg"
    assert _platform.media_binary("ffprobe") == "ffprobe"
    assert _platform.ytdlp_media_args() == []
    assert _platform.video_format("original") == "original"
    assert _platform.podcast_audio_format() == "mp3"
    assert "alignment" not in _platform.platform_capabilities()


def test_darwin_formats_reject_av1_and_unknown_codecs(darwin_bundle):
    # Exercise yt-dlp's own filter parser when installed; no download is made.
    yt_dlp = pytest.importorskip("yt_dlp")
    selector = _platform.video_format("unrestricted")
    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        choose = ydl.build_format_selector(selector)
        def selected(codec):
            return list(choose({"formats": [{"format_id": "test", "url": "https://invalid.test/media",
                       "vcodec": codec, "acodec": "none", "height": 360, "ext": "mp4"}],
                       "has_merged_format": False, "incomplete_formats": False}))
        for codec in ("av01.0.08M.08", "hevc", "none", None):
            assert not selected(codec)
        for codec in ("avc1.42001E", "h264", "vp9", "vp09.00.10.08", "vp8"):
            assert selected(codec)
    assert _platform.podcast_audio_format() == "wav"


def test_alignment_stays_separate_from_cli(darwin_bundle):
    assert _platform.alignment_capability()["code"] == "alignment_requires_torchcodec"
    notices = darwin_bundle / "Resources/notices"
    notices.mkdir()
    report = {"available": True, "libraries": ["libavcodec.61.dylib"]}
    (notices / "torchcodec.json").write_text(json.dumps(report))
    assert _platform.alignment_capability()["available"] is False
    libs = darwin_bundle / "Frameworks/FFmpeg7"
    libs.mkdir(parents=True)
    (libs / "libavcodec.61.dylib").touch()
    assert _platform.alignment_capability()["available"] is True


def test_torchcodec_rewrite_uses_loader_relative_ffmpeg7(tmp_path):
    binary = tmp_path / "Contents/Resources/Python/lib/python3.13/site-packages/torchcodec/libtorchcodec_core7.dylib"
    root = tmp_path / "Contents/Frameworks/FFmpeg7"
    commands = ("cmd LC_LOAD_DYLIB\nname @rpath/libavcodec.61.dylib (offset 24)\n"
                "cmd LC_LOAD_DYLIB\nname @rpath/libtorch.dylib (offset 24)\n")
    changes = ffmpeg_bundle.torchcodec_changes(commands, binary, root)
    assert len(changes) == 1
    assert changes[0][0] == "@rpath/libavcodec.61.dylib"
    assert (binary.parent / changes[0][1].removeprefix("@loader_path/")).resolve() == root / "libavcodec.61.dylib"


@pytest.mark.parametrize("supplied", ["bare", "bundle", "external"])
def test_podcast_download_uses_bundled_tools_and_wav(darwin_bundle, monkeypatch, tmp_path, supplied):
    import podcasts
    monkeypatch.setattr(podcasts, "sys", _platform.sys)
    monkeypatch.setattr(_platform, "media_capability", lambda: {"available": True})
    episode = {"id": 1, "title": "episode", "feed_id": 1,
               "audio_url": "https://podcast.test/audio.m4a", "status": podcasts.EPISODE_STATUS_QUEUED}
    feed = {"id": 1, "title": "feed"}
    monkeypatch.setattr(podcasts, "get_episode", lambda *args: episode)
    monkeypatch.setattr(podcasts, "get_feed", lambda *args: feed)
    monkeypatch.setattr(podcasts, "_record_audio_result", lambda *args, **kwargs: None)
    expected = podcasts._episode_audio_path(tmp_path, feed, episode)

    def run(command, **kwargs):
        assert command[command.index("--audio-format") + 1] == "wav"
        assert command[command.index("--ffmpeg-location") + 1] == str(darwin_bundle / "Helpers")
        assert command.count("--ignore-config") == 1
        assert command.count("--ffmpeg-location") == 1
        expected.write_bytes(b"generated WAV placeholder")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    import uoink_processes
    monkeypatch.setattr(uoink_processes, "run_owned", run)
    monkeypatch.setattr(podcasts.subprocess, "run", run)
    cmd = ["python", "-m", "yt_dlp"]
    if supplied == "bundle":
        cmd += _platform.ytdlp_media_args()
    elif supplied == "external":
        cmd += ["--ignore-config", "--ffmpeg-location=/opt/homebrew/bin"]
    result = podcasts.download_episode_audio(None, 1, data_root=tmp_path,
        ytdlp_cmd=cmd, resolve_url=lambda url, **kwargs: url)
    assert result["ok"] is True and Path(result["local_path"]).suffix == ".wav"


@pytest.mark.parametrize("succeeds", [True, False])
def test_torchcodec_install_retains_only_a_qualified_runtime(monkeypatch, tmp_path, succeeds):
    import build_bundle
    output, app = tmp_path / "build", tmp_path / "Uoink.app"
    notices = app / "Contents/Resources/notices"
    notices.mkdir(parents=True)
    (output / "notices").mkdir(parents=True)
    for name in ("ffmpeg", "ffprobe"):
        binary = output / "cli/bin" / name
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_bytes(b"CLI")
    for name, major in ff.LIBRARIES.items():
        binary = output / "shared/lib" / f"lib{name}.{major}.dylib"
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_bytes(b"\xcf\xfa\xed\xfelibrary")
    codec = app / "Contents/Resources/Python/lib/python3.13/site-packages/torchcodec/libtorchcodec_core7.dylib"
    codec.parent.mkdir(parents=True)
    original = b"\xcf\xfa\xed\xfeoriginal"
    codec.write_bytes(original)
    metadata = output / "shared/lib/pkgconfig/libavcodec.pc"
    metadata.parent.mkdir()
    metadata.write_text("build metadata")
    monkeypatch.setattr(ffmpeg_bundle, "verify_output", lambda *args: None)

    def run(command, **kwargs):
        if command[0] == "install_name_tool":
            Path(command[-1]).write_bytes(b"\xcf\xfa\xed\xfemodified")
        return SimpleNamespace(stdout="cmd LC_LOAD_DYLIB\nname @rpath/libavcodec.61.dylib (offset 24)\n")

    def probe(*args):
        assert args[0] == app / "Contents/Resources/Python/bin/python3"
        if not succeeds:
            raise RuntimeError("synthetic ABI mismatch")
        return {"available": True, "samples": 1600}

    monkeypatch.setattr(build_bundle, "run", run)
    monkeypatch.setattr(ffmpeg_bundle, "probe_torchcodec", probe)
    result = ffmpeg_bundle.install(output, app, notices)
    assert result["shared_bundled"] is succeeds
    assert (app / "Contents/Frameworks/FFmpeg7").exists() is succeeds
    if succeeds:
        assert all(p.suffix == ".dylib" for p in (app / "Contents/Frameworks/FFmpeg7").iterdir())
    assert (codec.read_bytes() == original) is (not succeeds)
    assert (app / "Contents/Helpers/ffmpeg").read_bytes() == b"CLI"
    report = json.loads((notices / "torchcodec.json").read_text())
    assert report["available"] is succeeds
    if not succeeds:
        assert "synthetic ABI mismatch" in report["reason"]


def test_ffmpeg_framework_directory_rejects_non_macho(monkeypatch, tmp_path):
    output, app = tmp_path / "build", tmp_path / "Uoink.app"
    notices = app / "Contents/Resources/notices"
    notices.mkdir(parents=True)
    (output / "notices").mkdir(parents=True)
    (output / "cli/bin").mkdir(parents=True)
    for name in ("ffmpeg", "ffprobe"):
        (output / "cli/bin" / name).write_bytes(b"fixture")
    (output / "shared/lib").mkdir(parents=True)
    (output / "shared/lib/not-native.dylib").write_text("not code")
    monkeypatch.setattr(ffmpeg_bundle, "verify_output", lambda *args: None)
    with pytest.raises(ValueError, match="Non-Mach-O"):
        ffmpeg_bundle.install(output, app, notices)
