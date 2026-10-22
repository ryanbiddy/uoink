"""Inspect nested archives without executing their payload; sign and repack code."""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import stat
import tarfile
import tempfile
import zipfile

from build_bundle import bundle_path, macho_files, run, sha256, signing_order, tree_inventory
from qualify_deps import write_json

ZIP_SUFFIXES = {".zip", ".whl", ".jar", ".egg"}
TAR_SUFFIXES = (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")


def archive_kind(path: Path) -> str | None:
    name = path.name.lower()
    # A tar containing a small ZIP may also pass is_zipfile's end-record probe.
    # Honor the enclosing tar before looking for a self-extracting ZIP trailer.
    if name.endswith(TAR_SUFFIXES):
        return "tar"
    if path.suffix.lower() in ZIP_SUFFIXES or zipfile.is_zipfile(path):
        return "zip"
    return None


def safe_name(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
        raise ValueError(f"Unsafe archive member: {name}")
    return path


def unpack(archive: Path, root: Path, kind: str, budget: list[int]) -> None:
    # Bound expansion across the entire recursive scan, including pure-data archives.
    def charge(size):
        budget[0] -= size
        if budget[0] < 0:
            raise ValueError("Nested archive expansion exceeds 8 GiB")

    if kind == "zip":
        with zipfile.ZipFile(archive) as source:
            seen = set()
            for entry in source.infolist():
                name = safe_name(entry.filename)
                if name in seen:
                    raise ValueError(f"Duplicate archive member: {name}")
                seen.add(name)
                charge(entry.file_size)
                target = root.joinpath(*name.parts)
                if stat.S_ISLNK(entry.external_attr >> 16):
                    link = source.read(entry).decode("utf-8")
                    if not bundle_path(target.parent / link, root):
                        raise ValueError(f"Archive symlink escapes payload: {name}")
        # ditto preserves resource forks and script signatures in AppleDouble records.
        run(["ditto", "-x", "-k", archive, root], timeout=600)
    else:
        with tarfile.open(archive) as source:
            for entry in source.getmembers():
                safe_name(entry.name)
                charge(entry.size)
            source.extractall(root, filter="data")
    tree_inventory(root)  # Includes lexical and resolved link containment.


def repack(root: Path, archive: Path, kind: str) -> None:
    replacement = archive.with_name(archive.name + ".signed")
    if kind == "zip":
        run(["ditto", "-c", "-k", "--sequesterRsrc", root, replacement], timeout=600)
    else:
        name = archive.name.lower()
        compression = "z" if name.endswith((".gz", ".tgz")) else (
            "j" if name.endswith((".bz2", ".tbz2")) else "J" if name.endswith((".xz", ".txz")) else "")
        run(["/usr/bin/tar", "--format", "pax", "--xattrs", f"-c{compression}f",
             replacement, "-C", root, "."], timeout=600)
    os.chmod(replacement, stat.S_IMODE(archive.stat().st_mode))
    os.replace(replacement, archive)


def sign_archives(app: Path, report: Path, sign) -> list[dict]:
    """Finish child archives before parent code, using the builder's signing order."""
    rows = []
    budget = [8 * 1024**3]
    write_json(report, rows)

    def visit(root: Path, prefix: str, depth: int) -> bool:
        if depth > 8:
            raise ValueError("Nested archive depth exceeds eight")
        changed = False
        for archive in sorted(root.rglob("*")):
            if archive.is_symlink() or not archive.is_file():
                continue
            kind = archive_kind(archive)
            if kind is None:
                continue
            label = prefix + archive.relative_to(root).as_posix()
            row = {"path": label, "kind": kind, "sha256_before": sha256(archive), "action": "scanning"}
            rows.append(row)
            write_json(report, rows)
            with tempfile.TemporaryDirectory(prefix="uoink-archive-") as temporary:
                extracted = Path(temporary)
                unpack(archive, extracted, kind, budget)
                children_changed = visit(extracted, label + "!/", depth + 1)
                natives = list(macho_files(extracted))
                row["mach_o"] = [p.relative_to(extracted).as_posix() for p in natives]
                write_json(report, rows)
                if natives or children_changed:
                    ordered = signing_order(extracted, require_main=False)
                    for path in ordered:
                        sign(path)
                    row["signed"] = [p.relative_to(extracted).as_posix() for p in ordered]
                    repack(extracted, archive, kind)
                    row["action"] = "signed-and-repacked"
                    changed = True
                else:
                    row["action"] = "unchanged-no-mach-o"
                row["sha256_after"] = sha256(archive)
                write_json(report, rows)
        return changed

    visit(app, "", 0)
    return rows
