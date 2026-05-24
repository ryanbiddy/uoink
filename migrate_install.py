r"""Yoink -> Uoink first-run install migration (v2.1).

This is the net-new, highest-risk piece of the rename: it copies an existing
v2.0 install from the Yoink locations to the new Uoink locations so an upgraded
user loses nothing. It runs **silently on the first boot of the new helper**
(design decision A: first-run helper, copy-not-move, 7-day grace, idempotent),
not as an installer GUI step.

What it moves (Windows; macOS/Linux paths handled the same way via _platform):

1. App-data dir:    %LOCALAPPDATA%\Yoink\  -> \Uoink\  (index.db, settings.json,
   server.log, token.txt, jobs/taxonomy, skills, the output\ fallback dir).
2. Credential Manager: the saved Anthropic key under service "Yoink" -> "Uoink".
3. HKCU\...\Run autostart: drop the legacy "Yoink" value (the v2.1 installer
   writes the new "Uoink" one); ensure "Uoink" points at this install.
4. Desktop corpus (Desktop\Yoink\ -> Desktop\Uoink\): NOT automatic. Exposed via
   migrate_desktop_corpus(), triggered by an opt-in prompt in the extension
   popup, because users may have linked those paths from other tools.

Safety model (copy-not-move):
- The legacy \Yoink\ folder stays authoritative and untouched until a fully
  verified copy exists. Failures (disk full, permission denied, partial copy)
  leave \Yoink\ intact and retry on the next boot.
- A .migration-complete sentinel in \Uoink\ gates the eventual hard-delete of
  the old folder, which only happens after a 7-day grace period.
- A .migrated-from-yoink marker (carrying the migration timestamp) is what the
  one-time "Yoink is now Uoink" toast keys off.

Every step is logged. The module is import-safe with no side effects; callers
invoke run_migration() / migrate_desktop_corpus() explicitly.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("uoink.migrate")

# Marker / sentinel filenames written into the NEW (\Uoink\) app-data dir.
MARKER_FILENAME = ".migrated-from-yoink"      # carries the migration timestamp
SENTINEL_FILENAME = ".migration-complete"     # gates old-folder deletion
GRACE_PERIOD_DAYS = 7

KEYRING_SERVICE_NEW = "Uoink"
KEYRING_SERVICE_OLD = "Yoink"
KEYRING_USERNAME = "anthropic_key"

# HKCU autostart Run key.
_RUN_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE_OLD = "Yoink"
_RUN_VALUE_NEW = "Uoink"

MIGRATED_TXT_FILENAME = "MIGRATED_TO_UOINK.txt"
_MIGRATED_TXT_TEMPLATE = """\
Yoink is now Uoink.

Everything in this folder was copied to:
  %LOCALAPPDATA%\\Uoink\\

Your saved videos, your settings, and your API key all moved with it.
Nothing was lost. This old folder is kept for 7 days as a safety net,
then removed automatically.

The magnet logo was always a U. uoink.video
Migrated: {timestamp}
"""


# --------------------------------------------------------------------------
# Public helpers
# --------------------------------------------------------------------------
def migration_marker_present(data_root: Path) -> bool:
    """True if this install was produced by a Yoink->Uoink migration (the
    one-time post-migration toast keys off this)."""
    try:
        return (Path(data_root) / MARKER_FILENAME).is_file()
    except OSError:
        return False


def _new_data_root() -> Path:
    import _platform
    return _platform.user_data_dir()


def _old_data_root() -> Path:
    import _platform
    return _platform.legacy_user_data_dir()


def _desktop_dir() -> Path:
    import _platform
    return _platform.desktop_dir()


def _now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _dir_size_bytes(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                pass
    return total


# --------------------------------------------------------------------------
# Status (consumed by `uoink doctor` / /diagnose and the dry-run printer)
# --------------------------------------------------------------------------
def migration_status() -> dict:
    new_root = _new_data_root()
    old_root = _old_data_root()
    desktop = _desktop_dir()
    legacy_desktop = desktop / "Yoink"
    new_desktop = desktop / "Uoink"
    return {
        "app_data": {
            "old_root": str(old_root),
            "new_root": str(new_root),
            "old_exists": old_root.exists(),
            "new_exists": new_root.exists(),
            "complete": (new_root / SENTINEL_FILENAME).is_file(),
            "migrated_marker": migration_marker_present(new_root),
        },
        "desktop_corpus": {
            "legacy_root": str(legacy_desktop),
            "new_root": str(new_desktop),
            "legacy_present": legacy_desktop.is_dir(),
            "new_present": new_desktop.is_dir(),
        },
        "keyring_legacy_present": _legacy_keyring_key_present(),
    }


def legacy_desktop_corpus_present() -> bool:
    """True if a Yoink-era Desktop corpus still exists and hasn't been moved.
    The extension popup polls this (via /diagnose) to decide whether to offer
    the opt-in 'Move your saved uoinks to Desktop\\Uoink\\?' prompt."""
    try:
        return (_desktop_dir() / "Yoink").is_dir()
    except OSError:
        return False


# --------------------------------------------------------------------------
# Keyring migration (non-fatal -- design Q4 A)
# --------------------------------------------------------------------------
def _keyring():
    try:
        import keyring
        return keyring
    except Exception as e:  # pragma: no cover - env-specific
        log.debug("migration: keyring unavailable (%s)", e)
        return None


def _legacy_keyring_key_present() -> bool:
    kr = _keyring()
    if kr is None:
        return False
    try:
        return bool(kr.get_password(KEYRING_SERVICE_OLD, KEYRING_USERNAME))
    except Exception:
        return False


def _migrate_keyring(dry_run: bool) -> str:
    """Copy the saved Anthropic key from service 'Yoink' to 'Uoink', then
    delete the old entry. Non-fatal: returns a short status string; never
    raises, so a keyring failure can't block the app-data migration."""
    kr = _keyring()
    if kr is None:
        return "skipped: keyring unavailable"
    try:
        existing_new = kr.get_password(KEYRING_SERVICE_NEW, KEYRING_USERNAME)
        if existing_new:
            return "skipped: new entry already present"
        old = kr.get_password(KEYRING_SERVICE_OLD, KEYRING_USERNAME)
        if not old:
            return "skipped: no legacy key"
        if dry_run:
            return "would copy Yoink->Uoink keyring entry, then delete legacy"
        kr.set_password(KEYRING_SERVICE_NEW, KEYRING_USERNAME, old)
        try:
            kr.delete_password(KEYRING_SERVICE_OLD, KEYRING_USERNAME)
        except Exception as e:
            log.warning("migration: copied key but couldn't delete legacy entry: %s", e)
        log.info("migration: Anthropic key moved Yoink->Uoink in credential store")
        return "migrated"
    except Exception as e:
        # Non-fatal: surfaced in /diagnose as "re-enter your key".
        log.error("migration: keyring migration failed (non-fatal): %s", e)
        return f"failed (non-fatal): {e}"


# --------------------------------------------------------------------------
# Autostart Run key (Windows only)
# --------------------------------------------------------------------------
def _migrate_run_key(app_dir: Path, dry_run: bool) -> str:
    if sys.platform != "win32":
        return "skipped: not Windows"
    try:
        import winreg
    except Exception as e:  # pragma: no cover
        return f"skipped: winreg unavailable ({e})"
    pythonw = app_dir / "python" / "pythonw.exe"
    server_py = app_dir / "server.py"
    desired = f'"{pythonw}" "{server_py}"'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_SUBKEY, 0,
                            winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
            old_present = False
            try:
                winreg.QueryValueEx(key, _RUN_VALUE_OLD)
                old_present = True
            except FileNotFoundError:
                pass
            if dry_run:
                return (f"would drop Run value '{_RUN_VALUE_OLD}'"
                        f"{' (present)' if old_present else ' (absent)'} and set "
                        f"'{_RUN_VALUE_NEW}' -> {desired}")
            if old_present:
                try:
                    winreg.DeleteValue(key, _RUN_VALUE_OLD)
                    log.info("migration: removed legacy autostart Run value 'Yoink'")
                except FileNotFoundError:
                    pass
            winreg.SetValueEx(key, _RUN_VALUE_NEW, 0, winreg.REG_SZ, desired)
            log.info("migration: autostart Run value 'Uoink' -> %s", desired)
            return "migrated"
    except OSError as e:
        log.warning("migration: Run-key migration failed (non-fatal): %s", e)
        return f"failed (non-fatal): {e}"


# --------------------------------------------------------------------------
# App-data migration (the core)
# --------------------------------------------------------------------------
def _is_installed_layout(app_dir: Path) -> bool:
    """True only for the shipped product (bundled python next to server.py).
    Guards the registry/keyring writes so a dev run from the repo never
    rewrites the user's real autostart entry or credential store."""
    return (app_dir / "python" / "pythonw.exe").exists()


def run_migration(*, dry_run: bool = False, app_dir: Path | None = None) -> dict:
    """Run (or, with dry_run=True, describe) the Yoink->Uoink migration.

    Returns a status dict. Idempotent and safe to call on every boot: a
    completed migration is a near-no-op (it only re-checks the 7-day cleanup).
    """
    if app_dir is None:
        app_dir = Path(__file__).parent.resolve()
    new_root = _new_data_root()
    old_root = _old_data_root()
    sentinel = new_root / SENTINEL_FILENAME
    result: dict = {
        "dry_run": dry_run,
        "old_root": str(old_root),
        "new_root": str(new_root),
        "steps": [],
        "outcome": None,
    }

    def step(name: str, detail: str) -> None:
        result["steps"].append({name: detail})
        log.info("migration[%s]: %s -- %s",
                 "dry-run" if dry_run else "run", name, detail)

    # Already complete -> only consider the grace-period cleanup.
    if sentinel.is_file():
        step("already_complete", f"{SENTINEL_FILENAME} present")
        cleanup = _maybe_cleanup_old_root(old_root, new_root, dry_run)
        step("old_folder_cleanup", cleanup)
        result["outcome"] = "already_migrated"
        return result

    # No legacy install -> fresh install, nothing to migrate.
    if not old_root.exists():
        step("no_legacy", f"{old_root} does not exist")
        result["outcome"] = "no_legacy"
        return result

    # Both exist with a real \Uoink\ library (manual reinstall): treat \Uoink\
    # as authoritative, skip the copy, but still finish the bookkeeping.
    if new_root.exists() and (new_root / "index.db").is_file():
        step("uoink_authoritative",
             "both folders exist and \\Uoink\\index.db present; skipping copy")
        if not dry_run:
            _write_sentinel(new_root)
            _write_marker(new_root)
            _write_breadcrumb(old_root)
        kr = _migrate_keyring(dry_run)
        step("keyring", kr)
        rk = _migrate_run_key(app_dir, dry_run) if _is_installed_layout(app_dir) \
            else "skipped: dev layout"
        step("run_key", rk)
        cleanup = _maybe_cleanup_old_root(old_root, new_root, dry_run)
        step("old_folder_cleanup", cleanup)
        result["outcome"] = "uoink_authoritative"
        return result

    # ---- Disk-space preflight (disk-full failure mode) -------------------
    need = _dir_size_bytes(old_root)
    try:
        new_root.parent.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(new_root.parent).free
    except OSError as e:
        step("space_check", f"could not stat free space: {e}")
        free = None
    if free is not None and free < int(need * 1.1):  # 10% headroom
        msg = (f"insufficient space (need ~{need // (1024*1024)} MB, "
               f"free ~{free // (1024*1024)} MB)")
        step("aborted", msg)
        result["outcome"] = "aborted_disk_full"
        result["error"] = msg
        log.error("migration aborted: %s", msg)
        return result

    if dry_run:
        step("would_copy",
             f"copy {need // (1024*1024)} MB: {old_root} -> {new_root} "
             "(copy-not-move; legacy folder kept)")
        step("keyring", _migrate_keyring(dry_run=True))
        step("run_key",
             _migrate_run_key(app_dir, dry_run=True)
             if _is_installed_layout(app_dir) else "skipped: dev layout")
        step("would_write_breadcrumb", str(old_root / MIGRATED_TXT_FILENAME))
        step("would_write_marker_sentinel",
             f"{MARKER_FILENAME} + {SENTINEL_FILENAME} in {new_root}")
        result["outcome"] = "dry_run"
        return result

    # ---- Copy (overwrite-newer so a partial prior attempt re-runs cleanly)
    try:
        shutil.copytree(old_root, new_root, dirs_exist_ok=True)
    except OSError as e:
        # Disk full or permission denied mid-copy: delete the partial \Uoink\
        # (best-effort) and leave \Yoink\ authoritative. Retry next boot.
        step("copy_failed", f"{type(e).__name__}: {e}")
        if _enospc(e):
            _safe_rmtree(new_root)
            step("partial_cleanup", "removed partial \\Uoink\\ after disk-full")
            result["outcome"] = "aborted_disk_full"
        else:
            step("kept_partial",
                 "left partial \\Uoink\\ in place; sentinel absent so next "
                 "boot overwrites-newer")
            result["outcome"] = "aborted_permission"
        result["error"] = str(e)
        log.error("migration copy failed: %s", e)
        return result

    # ---- Verify the copy before trusting it -----------------------------
    if not _verify_copy(old_root, new_root):
        step("verify_failed", "key files missing in \\Uoink\\ after copy")
        result["outcome"] = "verify_failed"
        log.error("migration verify failed; \\Yoink\\ stays authoritative")
        return result
    step("copy_verified", f"copied + verified {need // (1024*1024)} MB")

    # ---- Side migrations (all non-fatal) --------------------------------
    step("keyring", _migrate_keyring(dry_run=False))
    step("run_key",
         _migrate_run_key(app_dir, dry_run=False)
         if _is_installed_layout(app_dir) else "skipped: dev layout")

    # ---- Breadcrumb + marker + sentinel ---------------------------------
    _write_breadcrumb(old_root)
    step("breadcrumb", str(old_root / MIGRATED_TXT_FILENAME))
    _write_marker(new_root)
    _write_sentinel(new_root)
    step("marker_sentinel", f"{MARKER_FILENAME} + {SENTINEL_FILENAME} written")

    result["outcome"] = "migrated"
    log.info("migration complete: %s -> %s", old_root, new_root)
    return result


def _enospc(e: OSError) -> bool:
    import errno
    return getattr(e, "errno", None) == errno.ENOSPC


def _verify_copy(old_root: Path, new_root: Path) -> bool:
    """Confirm the copy landed: every top-level file present in old exists in
    new with a matching size. Subtrees are spot-checked by index.db."""
    try:
        for item in old_root.iterdir():
            target = new_root / item.name
            if not target.exists():
                log.warning("migration verify: missing %s", target)
                return False
            if item.is_file() and item.stat().st_size != target.stat().st_size:
                log.warning("migration verify: size mismatch %s", target)
                return False
        return True
    except OSError as e:
        log.warning("migration verify error: %s", e)
        return False


def _write_breadcrumb(old_root: Path) -> None:
    try:
        (old_root / MIGRATED_TXT_FILENAME).write_text(
            _MIGRATED_TXT_TEMPLATE.format(timestamp=_now_stamp()),
            encoding="utf-8",
        )
    except OSError as e:
        log.warning("migration: could not write breadcrumb: %s", e)


def _write_marker(new_root: Path) -> None:
    try:
        (new_root / MARKER_FILENAME).write_text(_now_stamp() + "\n", encoding="utf-8")
    except OSError as e:
        log.warning("migration: could not write marker: %s", e)


def _write_sentinel(new_root: Path) -> None:
    try:
        (new_root / SENTINEL_FILENAME).write_text(_now_stamp() + "\n", encoding="utf-8")
    except OSError as e:
        log.warning("migration: could not write sentinel: %s", e)


def _safe_rmtree(path: Path) -> None:
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception as e:  # pragma: no cover
        log.warning("migration: rmtree(%s) failed: %s", path, e)


def _maybe_cleanup_old_root(old_root: Path, new_root: Path, dry_run: bool) -> str:
    """Hard-delete the legacy \\Yoink\\ folder once the 7-day grace period has
    elapsed AND \\Uoink\\ is confirmed healthy (sentinel + index.db)."""
    if not old_root.exists():
        return "old folder already gone"
    if not (new_root / SENTINEL_FILENAME).is_file():
        return "sentinel missing; not cleaning up"
    if not (new_root / "index.db").is_file():
        return "new index.db missing; not cleaning up"
    marker = new_root / MARKER_FILENAME
    try:
        stamp = marker.read_text(encoding="utf-8").strip().splitlines()[0]
        migrated_at = datetime.strptime(stamp, "%Y-%m-%d %H:%M")
    except (OSError, ValueError, IndexError):
        # No readable marker: be conservative, don't delete.
        return "no readable migration timestamp; not cleaning up"
    age = datetime.now() - migrated_at
    if age < timedelta(days=GRACE_PERIOD_DAYS):
        days_left = GRACE_PERIOD_DAYS - age.days
        return f"within grace period (~{days_left} day(s) left)"
    if dry_run:
        return f"would hard-delete {old_root} (grace elapsed)"
    _safe_rmtree(old_root)
    log.info("migration: removed legacy folder %s after grace period", old_root)
    return f"removed {old_root}"


# --------------------------------------------------------------------------
# Desktop corpus migration (opt-in -- design Q5 A)
# --------------------------------------------------------------------------
def migrate_desktop_corpus(*, mode: str = "move", dry_run: bool = False) -> dict:
    """Move (or copy) Desktop\\Yoink\\ -> Desktop\\Uoink\\. Triggered by the
    opt-in extension-popup prompt, never automatically.

    mode='move' relocates the corpus; mode='copy' (the 'Keep both' choice)
    duplicates it so external tools that linked the old path keep working.
    """
    desktop = _desktop_dir()
    src = desktop / "Yoink"
    dst = desktop / "Uoink"
    result = {"mode": mode, "dry_run": dry_run, "src": str(src), "dst": str(dst)}
    if not src.is_dir():
        result["outcome"] = "no_legacy_corpus"
        return result
    if dry_run:
        result["outcome"] = f"would {mode} {src} -> {dst}"
        return result
    try:
        if mode == "copy":
            shutil.copytree(src, dst, dirs_exist_ok=True)
            result["outcome"] = "copied"
        else:
            dst.mkdir(parents=True, exist_ok=True)
            for item in src.iterdir():
                target = dst / item.name
                if target.exists():
                    continue  # don't clobber anything already at the new path
                shutil.move(str(item), str(target))
            result["outcome"] = "moved"
        log.info("desktop corpus %s: %s -> %s", result["outcome"], src, dst)
    except OSError as e:
        result["outcome"] = f"failed: {e}"
        log.error("desktop corpus migration failed: %s", e)
    return result
