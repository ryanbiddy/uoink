"""Copy source-stage inputs to disposable storage before running build.ps1."""
from pathlib import Path
import shutil


def copy_stage_source(destination: Path) -> Path:
    source = Path(__file__).resolve().parents[1]
    destination.mkdir()
    for path in source.glob("*.py"):
        shutil.copy2(path, destination / path.name)
    for name in ("build.ps1", "VERSION", "uoink", "uoink.cmd", "topics.json",
                 "requirements.txt", "requirements-installer-lock.txt",
                 "THIRD-PARTY-NOTICES.md"):
        shutil.copy2(source / name, destination / name)
    for name in ("helper", "uoink_core", "skills", "voice_dna", "assets", "cli",
                 "extension", "migrations", "defaults", "third-party-notices",
                 "installer/templates"):
        shutil.copytree(source / name, destination / name,
                        ignore=shutil.ignore_patterns("__pycache__", "node_modules"))
    (destination / "scripts").mkdir()
    for name in ("installer_signing.ps1", "install-watchdog.ps1", "recall_hook.py"):
        shutil.copy2(source / "scripts" / name, destination / "scripts" / name)
    for name in ("verify_install.ps1", "upgrade_prep.ps1"):
        shutil.copy2(source / "installer" / name, destination / "installer" / name)
    return destination
