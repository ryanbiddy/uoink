"""Import startup modules and inspect real MCP stdio replies in a fresh CI venv."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import runpy
import subprocess
import tempfile

from qualify_deps import ROOT, run_logged, sha256, verify_ui_wheels, wheel_details, write_json

COCOA_IMPORT = "import AppKit, Quartz, WebKit, Security, webview; import webview.platforms.cocoa as cocoa; assert cocoa.renderer == 'cocoa'; print('pywebview backend: cocoa (import only)')"


def local_source(root: Path, name: str) -> Path | None:
    path = root.joinpath(*name.split("."))
    for candidate in (path.with_suffix(".py"), path / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def startup_modules(root: Path, seeds: tuple[str, ...]) -> list[str]:
    """Follow all statically named local imports, including startup functions.

    This conservative superset also includes lazy feature paths. GUI entry
    modules are seeds because the installed helper launches them by filename.
    """
    pending = list(seeds)
    found = set()
    while pending:
        name = pending.pop()
        if name in found:
            continue
        source = local_source(root, name)
        if source is None:
            continue
        found.add(name)
        nodes = [ast.parse(source.read_text(encoding="utf-8-sig"))]
        while nodes:
            node = nodes.pop()
            imports = []
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    package = name.split(".") if source.name == "__init__.py" else name.split(".")[:-1]
                    base = ".".join(package[:len(package) - node.level + 1] + ([base] if base else []))
                imports = [base] + [f"{base}.{alias.name}" for alias in node.names]
            for imported in imports:
                # Include package initializers as well as the imported submodule.
                parts = imported.split(".")
                pending.extend(".".join(parts[:i]) for i in range(1, len(parts) + 1)
                               if local_source(root, ".".join(parts[:i])) is not None)
            nodes.extend(ast.iter_child_nodes(node))
    return sorted(found)


def isolated_env(support: dict, scratch: Path, toolset: str = "full") -> dict:
    # Reuse the real stdio regression's profile/port/output contract. It does
    # not set HOME, which Darwin needs in addition to XDG_DATA_HOME.
    env = support["_isolated_env"](str(scratch))
    for variable, relative in (("HOME", "home"), ("USERPROFILE", "home"),
                               ("APPDATA", "roaming"), ("XDG_CONFIG_HOME", "config"),
                               ("XDG_CACHE_HOME", "cache")):
        target = scratch / relative
        target.mkdir(exist_ok=True)
        env[variable] = str(target)
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
               UOINK_MCP_TOOLSET=toolset, PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
    env.pop("PYTHONPATH", None)  # No ambient SDK or user packages can rescue this venv.
    return env


def import_one(python: Path, name: str, support: dict, log: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="uoink-import-") as scratch:
        env = isolated_env(support, Path(scratch))
        command = [str(python), "-B", "-c",
                   "import sys, importlib; sys.path.insert(0, sys.argv[1]); "
                   "import uoink_install_isolation; uoink_install_isolation.apply_from_process(argv=[]); "
                   "importlib.import_module(sys.argv[2]); print('import OK:', sys.argv[2])",
                   str(ROOT), name]
        try:
            result = subprocess.run(command, cwd=scratch, env=env, capture_output=True,
                                    text=True, timeout=90, check=False)
            log.write_text(result.stdout + result.stderr, encoding="utf-8")
            return {"module": name, "ok": result.returncode == 0, "exit_code": result.returncode}
        except (subprocess.TimeoutExpired, OSError) as exc:
            log.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
            return {"module": name, "ok": False, "error": str(exc)}


def protocol_smoke(python: Path, mode: str, support: dict, output: Path) -> dict:
    result = {"toolset": mode, "ok": False, "count": None}
    client = None
    with tempfile.TemporaryDirectory(prefix=f"uoink-mcp-{mode}-") as scratch:
        try:
            client = support["_StdioClient"](
                [str(python), "-B", str(ROOT / "uoink_mcp.py")], scratch,
                isolated_env(support, Path(scratch), mode), timeout=120)
            client.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "mac-qualification", "version": "1"}}})
            init = client.wait_for(1)
            result["initialize"] = init
            if "result" not in init:
                raise AssertionError(f"initialize failed: {init}")
            client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            client.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            listed = client.wait_for(2)
            write_json(output / f"tools-{mode}.json", listed)
            names = [tool["name"] for tool in listed["result"]["tools"]]
            expected = support["CORE_STDIO_TOOLS"] if mode == "core" else support["CANONICAL_STDIO_TOOLS"]
            result.update(count=len(names), expected_count=len(expected), names=names)
            if len(names) != len(set(names)) or set(names) != set(expected):
                raise AssertionError("tools/list differs from the checked-in stdio inventory")
            version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
            if init["result"]["serverInfo"]["version"] != version:
                raise AssertionError("initialize does not report the product VERSION")
            result["ok"] = True
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            if client is not None:
                client.close()
                client.proc.wait(timeout=10)
                (output / f"stderr-{mode}.txt").write_text(
                    "\n".join(client.stderr_lines) + "\n", encoding="utf-8")
    print(f"MCP {mode}: count={result['count']} ok={result['ok']}", flush=True)
    return result


def select_wheels(directory: Path) -> list[Path]:
    selected = {}
    for path in sorted(directory.glob("*.whl")):
        info = wheel_details(path.name)
        # Both targets can yield different wheels for one pin. Use one per
        # distribution on the macOS 15 runner; prefer the lower advertised floor.
        floor = tuple(map(int, (info["minimum_macos_implied"] or "0.0").split(".")))
        key = info["package"]
        if key not in selected or floor < selected[key][0]:
            selected[key] = (floor, path)
    return [selected[key][1] for key in sorted(selected)]


def verify_complete_set(directory: Path, wheels: list[Path]) -> list[str]:
    """Job C must fail if B omitted a pin or artifact bytes changed in transit."""
    manifest = json.loads((directory / "wheel-manifest.json").read_text(encoding="utf-8"))
    errors = [str(error) for error in manifest["errors"]]
    expected = {row["filename"]: row["sha256"] for row in manifest["wheels"]}
    versions = {}
    for wheel in wheels:
        info = wheel_details(wheel.name)
        versions[info["package"]] = info["version"]
        if expected.get(wheel.name) != sha256(wheel):
            errors.append(f"Wheel hash mismatch or unreported artifact: {wheel.name}")
    # packaging is an explicit qualification/test dependency. Validation must
    # also work in interpreters that have pytest but no pip installation.
    from packaging.version import Version
    for pin in manifest["pins"]:
        actual = versions.get(pin["package"])
        if actual is None or Version(actual) != Version(pin["version"]):
            errors.append(f"Missing qualified pin: {pin['package']}=={pin['version']}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--wheels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    logs = output / "imports"
    logs.mkdir(exist_ok=True)
    wheels = select_wheels(args.wheels)
    report = {"selected_wheels": [path.name for path in wheels], "imports": [], "mcp": []}
    try:
        report["wheel_set_errors"] = verify_complete_set(args.wheels, wheels)
        verify_ui_wheels([{"filename": path.name, "sha256": sha256(path)} for path in wheels], complete=True)
    except (OSError, ValueError, KeyError) as exc:
        report["wheel_set_errors"] = [f"Invalid wheel manifest: {exc}"]
    if report["wheel_set_errors"]:
        write_json(output / "smoke.json", report)
        return 1
    base = [str(args.python), "-m", "pip", "--isolated", "install", "--no-index", "--no-deps",
            "--disable-pip-version-check"]
    code = run_logged(base + [str(path) for path in wheels], output / "install.txt", timeout=600) if wheels else 1
    report["install_exit_code"] = code
    if code and wheels:
        # An incompatible wheel must not prevent all remaining imports being probed.
        report["individual_installs"] = [{"wheel": path.name, "exit_code": run_logged(
            base + [str(path)], output / f"install-{i}.txt")} for i, path in enumerate(wheels)]
    report["pip_check_exit_code"] = run_logged(
        [str(args.python), "-m", "pip", "check"], output / "pip-check.txt")
    report["cocoa_import_exit_code"] = run_logged(
        [str(args.python), "-B", "-c", COCOA_IMPORT], output / "cocoa-import.txt")
    support = runpy.run_path(str(ROOT / "tests/test_c01_mcp_stdio.py"), run_name="mac_smoke_support")
    seeds = ("server", "uoink_mcp", "uoink_tray", "uoink_splash", "uoink_dashboard", "helper.mac_menubar")
    report["module_discovery"] = {"method": "recursive static local imports, including function bodies", "seeds": seeds}
    for name in startup_modules(ROOT, seeds):
        row = import_one(args.python, name, support, logs / f"{name}.txt")
        report["imports"].append(row)
        print(f"import {name}: ok={row['ok']}", flush=True)
        write_json(output / "smoke.json", report)
    for mode in ("full", "core"):
        report["mcp"].append(protocol_smoke(args.python, mode, support, output))
        write_json(output / "smoke.json", report)
    return int(bool(code) or bool(report["pip_check_exit_code"]) or bool(report["cocoa_import_exit_code"]) or
               any(not row["ok"] for row in report["imports"] + report["mcp"]))


if __name__ == "__main__":
    raise SystemExit(main())
