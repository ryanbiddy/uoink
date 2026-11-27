"""Locate client settings and merge a single named JSON server entry."""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from uoink_core.storage import checked_path, pinned_parent, read_checked_bytes


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
    root: Path
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


def _settings_root(path):
    roots = [roaming_dir(), Path.home(), Path.cwd()]
    for name in ("LOCALAPPDATA", "COPILOT_HOME"):
        if os.environ.get(name):
            roots.append(Path(os.environ[name]).absolute())
    for root in sorted(roots, key=lambda root: len(root.parts), reverse=True):
        if path.is_relative_to(root):
            return root
    raise ConfigError("The settings file is outside the recognized client configuration folders.", 409)


def _read(path: Path, *, root=None) -> bytes | None:
    if path.is_symlink():
        raise ConfigError("The settings file is a symbolic link. Merge the printed recipe into its target.", 409)
    try:
        return read_checked_bytes(root, path) if root is not None else path.read_bytes()
    except FileNotFoundError:
        return None


def _invalid_constant(value):
    raise ValueError(f"{value} is not a JSON number")


def plan_edit(path: Path, label: str, section: str, entry: dict) -> ConfigEdit:
    try:
        root = _settings_root(path)
        checked_path(root, path.parent)
        original = _read(path, root=root)
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
        if original and b"\r\n" in original:
            replacement = replacement.replace(b"\n", b"\r\n")
    except ConfigError:
        raise
    except (ValueError, RecursionError) as exc:
        raise ConfigError(f"Couldn't merge the {label} settings. Check for invalid JSON or duplicate keys. "
                          "If it uses comments, run uoink connect without --write and merge the printed entry.", 422) from exc
    return ConfigEdit(root, path, original, replacement, action)


def _discard(staged: Path):
    try:
        staged.unlink(missing_ok=True)
    except PermissionError:
        try:
            if not staged.is_symlink():
                staged.chmod(0o600)
                staged.unlink(missing_ok=True)
        except OSError:
            pass
    except OSError:
        pass


def _staged_file(path: Path, cleanup: ExitStack) -> Path:
    # A unique sibling makes replace atomic without following an old .tmp or .bak link.
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", delete=False) as f:
        staged = Path(f.name)
    cleanup.callback(_discard, staged)
    return staged


def _check_original(path: Path, expected: bytes | Path | None, label: str):
    current = path.readlink() if isinstance(expected, Path) and path.is_symlink() else _read(path)
    if current != expected:
        raise ConfigError(f"The {label} settings changed. Review the new settings and try again.", 409)


def _stage_bytes(path: Path, data: bytes, cleanup: ExitStack) -> Path:
    staged = _staged_file(path, cleanup)
    with staged.open("wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    return staged


def _stage_copy(path: Path, expected: bytes, cleanup: ExitStack, label: str) -> Path:
    if not path.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
        raise ConfigError(f"The {label} settings or backup file is read-only. Check its permissions.")
    staged = _staged_file(path, cleanup)
    # Hold a writable descriptor for fsync even if copy2 copies a read-only attribute.
    with staged.open("r+b") as f:
        shutil.copy2(path, staged)
        os.fsync(f.fileno())
    _check_original(staged, expected, label)
    return staged


@dataclass
class _PendingWrite:
    path: Path
    before: bytes | Path | None
    after: bytes
    staged: Path
    restore: Path | None
    backup: Path | None = None


def _previous_backup(backup: Path, cleanup: ExitStack, label: str):
    # The previous writer could replace a .bak symlink. Save the link itself
    # for rollback without ever opening its target.
    if backup.is_symlink():
        target = backup.readlink()
        attributes = getattr(backup.lstat(), "st_file_attributes", 0)
        restore = _staged_file(backup, cleanup)
        restore.unlink()
        restore.symlink_to(target, target_is_directory=bool(attributes & stat.FILE_ATTRIBUTE_DIRECTORY))
        return target, restore
    before = _read(backup)
    return before, None if before is None else _stage_copy(backup, before, cleanup, label)


def apply_edits(edits: list[ConfigEdit], label: str) -> None:
    """Prepare every file and backup before replacing any settings."""
    with ExitStack() as cleanup:
        configs = []
        backups = []
        applied = []
        try:
            for edit in edits:
                directory = cleanup.enter_context(pinned_parent(edit.root, edit.path, create=True))
                path = directory / edit.path.name
                _check_original(path, edit.original, label)
                new = _stage_bytes(path, edit.replacement, cleanup)
                restore = None
                if edit.original is not None:
                    backup = directory / edit.backup.name
                    try:
                        original_copy = _stage_copy(path, edit.original, cleanup, label)
                        previous, previous_copy = _previous_backup(backup, cleanup, label)
                    except OSError as exc:
                        raise ConfigError(f"Couldn't back up the {label} settings.") from exc
                    backups.append(_PendingWrite(backup, previous, edit.original, original_copy, previous_copy))
                    restore = _stage_bytes(path, edit.original, cleanup)
                    shutil.copymode(path, restore)
                    shutil.copymode(path, new)
                configs.append(_PendingWrite(path, edit.original, edit.replacement, new, restore,
                                             directory / edit.backup.name if edit.backup else None))

            pending = backups + configs
            for item in pending:
                _check_original(item.path, item.before, label)
            for item in pending:
                _check_original(item.path, item.before, label)
                item.staged.replace(item.path)
                applied.append(item)
        except (OSError, ConfigError) as exc:
            # Restore configs before their backups. Keep the recovery copy if a restore fails.
            keep_backups = set()
            incomplete = False
            for item in reversed(applied):
                if item.path in keep_backups:
                    continue
                try:
                    _check_original(item.path, item.after, label)
                    if item.restore is None:
                        item.path.unlink()
                    else:
                        item.restore.replace(item.path)
                except (OSError, ConfigError):
                    incomplete = True
                    if item.backup is not None:
                        keep_backups.add(item.backup)
            if incomplete:
                message = str(exc) if isinstance(exc, ConfigError) else f"Couldn't save the {label} settings."
                raise ConfigError(message + " Couldn't restore all files. Check the settings and their .bak copies.",
                                  getattr(exc, "http_status", 500)) from exc
            if isinstance(exc, ConfigError):
                raise
            raise ConfigError(f"Couldn't save the {label} settings. Check file permissions and try again.") from exc
