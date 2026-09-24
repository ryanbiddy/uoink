"""Every reachable first-party import must be staged AND installed."""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ISS = (ROOT / "installer" / "uoink.iss").read_text(encoding="utf-8")
BUILD = (ROOT / "build.ps1").read_text(encoding="utf-8")
ENTRYPOINTS = ("server", "index", "uoink_mcp", "uoink_mcp_tools")


def reachable_modules(root: Path, entrypoints=ENTRYPOINTS) -> set[Path]:
    """AST walk includes deferred, conditional, nested and relative imports."""
    seen = set()
    pending = list(entrypoints)
    while pending:
        name = pending.pop()
        base = root.joinpath(*name.split("."))
        path = base.with_suffix(".py")
        if not path.is_file():
            path = base / "__init__.py"
        if not path.is_file() or path in seen:
            continue
        seen.add(path)
        package = name if path.name == "__init__.py" else name.rpartition(".")[0]
        if "." in name:
            pending.append(name.rpartition(".")[0])
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if isinstance(node, ast.Import):
                pending.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                prefix = node.module or ""
                if node.level:
                    parts = package.split(".")
                    prefix = ".".join(parts[:len(parts) - node.level + 1] + ([prefix] if prefix else []))
                if prefix:
                    pending.append(prefix)
                    pending.extend(prefix + "." + alias.name for alias in node.names if alias.name != "*")
    return {path.relative_to(root) for path in seen}


def staged_sources() -> set[str]:
    return {name.replace("\\", "/") for name in re.findall(
        r"(?m)^Copy-Item \(Join-Path \$RepoRoot '([^']+)'\)", BUILD)}


def installed_sources() -> set[str]:
    files_section = ISS.split("[Files]", 1)[1].split("\n[", 1)[0]
    return {name.replace("\\", "/") for name in re.findall(
        r'^Source: "staging\\([^"]+)";', files_section, re.M)}


def test_every_server_import_is_in_installer_and_staging():
    staged, installed = staged_sources(), installed_sources()
    missing = []
    for path in sorted(reachable_modules(ROOT)):
        name = path.as_posix()
        ancestors = [parent.as_posix() for parent in path.parents if parent != Path(".")]
        if name not in staged and not any(parent in staged for parent in ancestors):
            missing.append(f"not staged: {name}")
        if name not in installed and not any(parent + "/*" in installed for parent in ancestors):
            missing.append(f"not installed: {name}")
    assert not missing, "\n".join(missing)


def test_import_walker_follows_deferred_and_relative_imports(tmp_path):
    (tmp_path / "server.py").write_text("def deferred():\n    import child\n")
    (tmp_path / "child.py").write_text("from pkg import inner\n")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "inner.py").write_text("from . import sibling\n")
    (tmp_path / "pkg" / "sibling.py").write_text("import json\n")
    assert {p.as_posix() for p in reachable_modules(tmp_path, ("server",))} == {
        "server.py", "child.py", "pkg/__init__.py", "pkg/inner.py", "pkg/sibling.py"}


def test_cli_and_watchdog_assets_are_in_both_lists():
    # Run F acceptance case 5: the Recall hook's own docstring points users at
    # the installed scripts/ path, so it must ship with the app.
    required = {"uoink", "uoink.cmd", "scripts/install-watchdog.ps1",
                "scripts/recall_hook.py"}
    assert required <= staged_sources()
    assert required <= installed_sources()


if __name__ == "__main__":
    test_every_server_import_is_in_installer_and_staging()
    test_cli_and_watchdog_assets_are_in_both_lists()
