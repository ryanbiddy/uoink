"""Disposable isolation-aware product overlay for source-runtime checks.

Copies product modules into a scratch app, overlays the archived isolation
module, and injects apply_from_process / data_root bindings. The archived
stop CLI is never invoked. This is not installed credit.
"""
from __future__ import annotations

import shutil
from pathlib import Path

_HERE = Path(__file__).resolve().parent
ARCHIVED_ISOLATION_PATCH = (
    _HERE.parents[1] / "docs" / "library" / "proof"
    / "ryan-install-review-2026-09-09" / "original.patch"
)
ISOLATION_MODULE_NAME = "uoink_install_isolation.py"

MCP_INJECT = (
    "import uoink_install_isolation as _install_isolation  # noqa: E402\n"
    "_install_isolation.apply_from_process()\n"
)
SERVER_INJECT = (
    "# Isolation must be validated before any later import can open default data.\n"
    "import uoink_install_isolation as _install_isolation  # noqa: E402\n"
    "_install_isolation.apply_from_process()\n"
)


def extract_new_file_from_patch(patch: Path, name: str) -> str:
    text = patch.read_text(encoding="utf-8")
    marker = f"diff --git a/{name} b/{name}"
    start = text.find(marker)
    if start < 0:
        raise FileNotFoundError(f"{name} not in {patch}")
    rest = text[start:]
    next_diff = rest.find("\ndiff --git ", 1)
    body = rest if next_diff < 0 else rest[:next_diff]
    lines = []
    seen_hunk = False
    for line in body.splitlines(keepends=True):
        if line.startswith("@@"):
            seen_hunk = True
            continue
        if not seen_hunk:
            continue
        if line.startswith("+"):
            lines.append(line[1:])
        elif line.startswith("\\"):
            continue
        elif line.startswith("-"):
            continue
        else:
            # context line in a new-file patch should not appear
            if line.startswith(" "):
                lines.append(line[1:])
    return "".join(lines)


_SCRATCH_EXCLUDE = {
    "build", ".git", "_scratch", "__pycache__", ".venv", "venv", "node_modules",
    ".pytest_cache", ".mypy_cache", "dist", "python", "bin", "Lib", "Scripts",
}


def _copy_product(src: Path, dest: Path) -> list[str]:
    dest.mkdir(parents=True, exist_ok=True)
    copied = []
    for path in src.iterdir():
        if path.name.startswith(".") or path.name in _SCRATCH_EXCLUDE:
            continue
        if path.is_dir():
            continue
        if path.suffix == ".py" or path.name in {"VERSION"}:
            shutil.copy2(path, dest / path.name)
            copied.append(path.name)
    for relative in ("helper", "uoink_core", "migrations", "defaults", "voice_dna"):
        origin = src / relative
        if origin.is_dir():
            shutil.copytree(
                origin, dest / relative, dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"),
            )
            copied.append(relative + "/")
    scripts_src = src / "scripts" / "recall_hook.py"
    if scripts_src.is_file():
        (dest / "scripts").mkdir(exist_ok=True)
        shutil.copy2(scripts_src, dest / "scripts" / "recall_hook.py")
        copied.append("scripts/recall_hook.py")
    return copied


def _inject_mcp(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if "uoink_install_isolation" in text:
        return "already_present"
    needle = "if _APP_DIR not in sys.path:\n    sys.path.insert(0, _APP_DIR)\n"
    if needle not in text:
        raise ValueError("uoink_mcp.py pin site not found; refusing silent inject")
    path.write_text(text.replace(needle, needle + "\n" + MCP_INJECT + "\n", 1), encoding="utf-8")
    return "injected"


def _inject_server(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    notes = {}
    if "uoink_install_isolation" not in text:
        needle = "HERE = Path(__file__).parent.resolve()\nsys.path.insert(0, str(HERE))\n"
        if needle not in text:
            raise ValueError("server.py HERE pin not found; refusing silent inject")
        text = text.replace(needle, needle + "\n" + SERVER_INJECT + "\n", 1)
        notes["apply"] = "injected"
    else:
        notes["apply"] = "already_present"
    if "PORT = 5179" in text and "listen_port" not in text.split("PORT =", 1)[1][:80]:
        text = text.replace("PORT = 5179", "PORT = _install_isolation.listen_port(5179)", 1)
        notes["port"] = "injected"
    if "TOKEN_PATH = HERE / \"token.txt\"" in text:
        text = text.replace(
            "TOKEN_PATH = HERE / \"token.txt\"",
            "_ISOLATION = _install_isolation.current_binding()\n"
            "TOKEN_PATH = (\n"
            "    _ISOLATION.token_path if _ISOLATION is not None else HERE / \"token.txt\"\n"
            ")",
            1,
        )
        notes["token"] = "injected"
    if "DATA_ROOT = _platform.user_data_dir()" in text and "data_root(_platform" not in text:
        text = text.replace(
            "DATA_ROOT = _platform.user_data_dir()",
            "DATA_ROOT = _install_isolation.data_root(_platform.user_data_dir())",
            1,
        )
        notes["data_root"] = "injected"
    path.write_text(text, encoding="utf-8")
    return notes


def provision_isolation_scratch(*, product_src: Path, scratch_app: Path,
                                patch: Path | None = None) -> dict:
    """Build a disposable isolation-aware source copy. Do not run stop."""
    patch = patch or ARCHIVED_ISOLATION_PATCH
    if scratch_app.exists():
        raise FileExistsError(f"scratch app already exists; preserve it: {scratch_app}")
    copied = _copy_product(product_src, scratch_app)
    module = extract_new_file_from_patch(patch, ISOLATION_MODULE_NAME)
    (scratch_app / ISOLATION_MODULE_NAME).write_text(module, encoding="utf-8", newline="\n")
    mcp_note = _inject_mcp(scratch_app / "uoink_mcp.py")
    server_note = _inject_server(scratch_app / "server.py")
    return {
        "scratch_app": str(scratch_app),
        "copied": copied,
        "isolation_module_bytes": len(module.encode("utf-8")),
        "isolation_patch": str(patch),
        "mcp_inject": mcp_note,
        "server_inject": server_note,
        "stop_cli_invoked": False,
        "installed_credit": False,
        "runtime_mode": "source-runtime",
        "excluded": sorted(_SCRATCH_EXCLUDE),
        "preserves_current_product_source": True,
        "note": (
            "Archived isolation overlay for bounded original-route development only. "
            "Current product source including the existing-preview reader is copied "
            "unchanged except the isolation inject pins."
        ),
    }
