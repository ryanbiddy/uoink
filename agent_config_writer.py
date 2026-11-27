"""Locate client settings and merge a single named JSON server entry."""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


class ConfigError(ValueError):
    def __init__(self, message: str, status: int = 500):
        super().__init__(message)
        self.http_status = status


def roaming_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData/Roaming")
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def claude_desktop_paths() -> list[Path]:
    name = "claude_desktop_config.json"
    classic = roaming_dir() / "Claude" / name
    if sys.platform != "win32":
        return [classic]
    local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
    cached = [pkg / "LocalCache/Roaming/Claude" / name
              for pkg in sorted((local / "Packages").glob("Claude_*"))]
    existing = [path for path in [classic, *cached] if path.exists()]
    if existing:
        return existing
    return [next((path for path in cached if path.parent.is_dir()), classic)]


def cline_storage() -> Path:
    return roaming_dir() / "Code/User/globalStorage/saoudrizwan.claude-dev"


def cline_config() -> Path:
    return cline_storage() / "settings/cline_mcp_settings.json"


@dataclass
class ConfigEdit:
    path: Path
    original: bytes | None
    replacement: bytes
    action: str

    @property
    def backup(self) -> Path | None:
        if self.original is not None:
            return self.path.with_suffix(self.path.suffix + ".bak")
        return None


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _read(path: Path) -> bytes | None:
    if path.is_symlink():
        raise ConfigError("The settings file is a symbolic link. Merge the printed recipe into its target.", 409)
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _invalid_constant(value):
    raise ValueError(f"{value} is not a JSON number")


def plan_edit(path: Path, label: str, section: str, entry: dict) -> ConfigEdit:
    try:
        original = _read(path)
    except OSError as exc:
        raise ConfigError(f"Couldn't read the {label} settings.") from exc
    try:
        data = {} if original is None else json.loads(
            original.decode("utf-8-sig"), object_pairs_hook=_unique_keys, parse_constant=_invalid_constant)
        if not isinstance(data, dict) or not isinstance(data.get(section, {}), dict):
            raise ConfigError(f"{label} settings and its {section} field must be JSON objects.", 422)
        servers = data.setdefault(section, {})
        action = "updated" if "uoink" in servers else "added"
        servers["uoink"] = entry
        replacement = (json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    except ConfigError:
        raise
    except (ValueError, RecursionError) as exc:
        raise ConfigError(f"Couldn't merge the {label} settings. Check the file for invalid JSON "
                          "or duplicate keys and try again.", 422) from exc
    return ConfigEdit(path, original, replacement, action)


def _staged_file(path: Path, cleanup: ExitStack) -> Path:
    # A unique sibling makes replace atomic without following an old .tmp or .bak link.
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", delete=False) as f:
        staged = Path(f.name)
    cleanup.callback(staged.unlink, missing_ok=True)
    return staged


def _check_original(edit: ConfigEdit, label: str):
    if _read(edit.path) != edit.original:
        raise ConfigError(f"The {label} settings changed. Review the new settings and try again.", 409)


def apply_edits(edits: list[ConfigEdit], label: str) -> None:
    """Prepare every file and backup before replacing any settings."""
    with ExitStack() as cleanup:
        staged = []
        applied = []
        try:
            for edit in edits:
                _check_original(edit, label)
                edit.path.parent.mkdir(parents=True, exist_ok=True)
                new = _staged_file(edit.path, cleanup)
                new.write_bytes(edit.replacement)
                if edit.backup is not None:
                    backup = _staged_file(edit.backup, cleanup)
                    try:
                        shutil.copy2(edit.path, backup)
                        if backup.read_bytes() != edit.original:
                            raise ConfigError(f"The {label} settings changed. Try again.", 409)
                        backup.replace(edit.backup)
                    except OSError as exc:
                        raise ConfigError(f"Couldn't back up the {label} settings.") from exc
                    shutil.copymode(edit.path, new)
                staged.append((edit, new))
            for edit, new in staged:
                _check_original(edit, label)
                new.replace(edit.path)
                applied.append(edit)
        except (OSError, ConfigError) as exc:
            # A later destination may be locked by the client. Undo only our own edit.
            for edit in reversed(applied):
                try:
                    if _read(edit.path) != edit.replacement:
                        raise OSError("file changed")
                    if edit.backup is None:
                        edit.path.unlink()
                    else:
                        restore = _staged_file(edit.path, cleanup)
                        restore.write_bytes(edit.original)
                        shutil.copymode(edit.path, restore)
                        restore.replace(edit.path)
                except (OSError, ConfigError) as rollback:
                    raise ConfigError(f"Couldn't restore all {label} settings. "
                                      "Check the config files and their .bak copies.") from rollback
            if isinstance(exc, ConfigError):
                raise
            raise ConfigError(f"Couldn't save the {label} settings. Check file permissions and try again.") from exc
