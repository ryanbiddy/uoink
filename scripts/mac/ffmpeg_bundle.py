"""Install FFmpeg and qualify TorchCodec without loader environment overrides."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from build_ffmpeg import LIBRARIES, load_config, verify_output, write_json

# Executed by the bundled interpreter, once at assembly and again after relocation.
# Keep the generated input and native-library evidence independent of model downloads.
TORCHCODEC_PROBE = r'''
import ctypes, importlib.metadata, json, pathlib, re, sys, wave
root, scratch = map(pathlib.Path, sys.argv[1:])
assert importlib.metadata.version("torchcodec").split("+")[0] == "0.7.0"
source = scratch / "torchcodec-input.wav"
with wave.open(str(source), "wb") as audio:
    audio.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
    audio.writeframes(b"\x10\x00" * 800)
from torchcodec.decoders import AudioDecoder
samples = AudioDecoder(str(source), sample_rate=16000, num_channels=1).get_all_samples()
assert samples.sample_rate == 16000 and tuple(samples.data.shape) == (1, 1600)
assert samples.data.isfinite().all() and samples.data.abs().sum() > 0
dyld = ctypes.CDLL(None)
dyld._dyld_image_count.restype = ctypes.c_uint32
dyld._dyld_get_image_name.argtypes = [ctypes.c_uint32]
dyld._dyld_get_image_name.restype = ctypes.c_char_p
loaded = [dyld._dyld_get_image_name(i).decode() for i in range(dyld._dyld_image_count())]
loaded = [p for p in loaded if re.match(r"lib(?:avcodec|avformat|avutil|avfilter|avdevice|swresample|swscale)\.", pathlib.Path(p).name)]
assert loaded, "TorchCodec loaded no FFmpeg libraries"
assert all(pathlib.Path(p).resolve().is_relative_to(root.resolve()) for p in loaded), loaded
print(json.dumps({"available": True, "loaded_libraries": loaded, "samples": 1600}))
'''


def probe_torchcodec(python: Path, library_root: Path, scratch: Path, env: dict) -> dict:
    env = {k: v for k, v in env.items() if not k.startswith("DYLD_") and k not in {
        "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"}}
    env.update(PATH="/usr/bin:/bin:/usr/sbin:/sbin", PYTHONDONTWRITEBYTECODE="1",
               PYTHONNOUSERSITE="1", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    result = subprocess.run([str(python), "-B", "-s", "-c", TORCHCODEC_PROBE,
                             str(library_root), str(scratch)], env=env, cwd=scratch,
                            capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f"TorchCodec decode exited {result.returncode}: {result.stderr[-8000:]}")
    return json.loads(result.stdout.strip().splitlines()[-1])


def torchcodec_changes(commands: str, binary: Path, library_root: Path) -> list[tuple[str, str]]:
    from build_bundle import native_loader_paths
    names = {f"lib{name}.{major}.dylib" for name, major in LIBRARIES.items()}
    relative = os.path.relpath(library_root, binary.parent).replace(os.sep, "/")
    return [(value, f"@loader_path/{relative}/{Path(value).name}")
            for kind, value in native_loader_paths(commands)
            if kind == "dependency" and Path(value).name in names]


def install(output: Path, app: Path, notices: Path) -> dict:
    from build_bundle import PYTHON_ROOT, PYTHON_EXECUTABLE, macho_files, native_loader_paths, run
    config = load_config()
    verify_output(output, config)
    contents = app / "Contents"
    helpers = contents / "Helpers"
    helpers.mkdir()
    for name in ("ffmpeg", "ffprobe"):
        shutil.copy2(output / "cli/bin" / name, helpers / name)
        (helpers / name).chmod(0o755)
    shutil.copytree(output / "notices", notices / "ffmpeg")
    # Always use this revision's docs, including when build output is cached.
    for name in ("FFMPEG.md", "build_ffmpeg.py", "ffmpeg_bundle.py", "payload.json"):
        shutil.copyfile(Path(__file__).parent / name, notices / "ffmpeg" / name)
    libraries = contents / "Frameworks/FFmpeg7"
    libraries.mkdir(parents=True)
    for path in (output / "shared/lib").glob("*.dylib"):
        shutil.copy2(path, libraries / path.name, follow_symlinks=False)
    natives = {path.resolve() for path in macho_files(libraries)}
    for path in libraries.iterdir():
        if path.resolve() not in natives:
            raise ValueError(f"Non-Mach-O file in FFmpeg7: {path}")
    majors = [f"lib{name}.{major}.dylib" for name, major in LIBRARIES.items()]
    for name in majors:
        if not (libraries / name).is_file():
            raise ValueError(f"Missing FFmpeg 7 ABI library: {name}")
    for binary in macho_files(libraries):
        run(["install_name_tool", "-id", f"@rpath/{binary.name}", binary])
        commands = run(["otool", "-l", binary], capture_output=True).stdout
        for kind, old in native_loader_paths(commands):
            if kind == "dependency" and (libraries / Path(old).name).is_file():
                run(["install_name_tool", "-change", old, f"@loader_path/{Path(old).name}", binary])
        run(["codesign", "--force", "--sign", "-", binary])
    original = {}
    report = {"available": False, "code": "alignment_requires_torchcodec", "libraries": []}
    try:
        packages = list((app / PYTHON_ROOT / "lib").glob("python*/site-packages/torchcodec"))
        patched = []
        for package in packages:
            for binary in macho_files(package):
                commands = run(["otool", "-l", binary], capture_output=True).stdout
                changes = torchcodec_changes(commands, binary, libraries)
                is_seven = bool(re.search(r"7(?:\.|$)", binary.name))
                if not changes and not is_seven:
                    continue
                original[binary] = binary.read_bytes()
                for old, new in changes:
                    run(["install_name_tool", "-change", old, new, binary])
                rpath = "@loader_path/" + os.path.relpath(libraries, binary.parent).replace(os.sep, "/")
                if ("rpath", rpath) not in native_loader_paths(commands):
                    run(["install_name_tool", "-add_rpath", rpath, binary])
                run(["codesign", "--force", "--sign", "-", binary])
                patched.append({"file": binary.relative_to(app).as_posix(), "changes": changes, "rpath": rpath})
        if not patched:
            raise RuntimeError("The qualified wheel contains no FFmpeg 7 TorchCodec Mach-O payload")
        python = app / PYTHON_EXECUTABLE
        with tempfile.TemporaryDirectory(prefix="uoink-torchcodec-") as tmp:
            report.update(probe_torchcodec(python, libraries, Path(tmp), os.environ.copy()))
        report.update(code=None, libraries=majors, patched=patched)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        # CLI remains usable. Restore the original wheel; don't ship an unproven ABI.
        for binary, data in original.items():
            binary.write_bytes(data)
        if libraries.resolve().parent != (contents / "Frameworks").resolve():
            raise ValueError("Refusing to remove an unexpected FFmpeg7 directory")
        shutil.rmtree(libraries)
        report.update(available=False, reason=str(error), libraries=[])
    write_json(notices / "torchcodec.json", report)
    return {"bundled": True, "cli": config["cli"], "shared": config["shared"],
            "shared_bundled": report["available"], "minimum_macos": config["minimum_macos"],
            "build_records": "ffmpeg/{cli,shared}/build.json", "torchcodec": report}
