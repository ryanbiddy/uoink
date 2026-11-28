"""Filesystem helpers for checked library reads and atomic publication."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
import json
import logging
import os
import re
import stat
import sys
import time
import uuid
from pathlib import Path

log = logging.getLogger("uoink.storage")

# Characters Windows forbids in a path component (plus control chars); used to
# sanitize a topic string into a safe folder name.
_FORBIDDEN_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


COMMENTS_START_MARK = "<!-- yoink:comments-start -->"
COMMENTS_END_MARK = "<!-- yoink:comments-end -->"
_PENDING_COMMENT = "*Fetching comments... they'll appear here when ready.*"
_LITE_COMMENT = "*Lite captures skip comments.*"


def _redirected(entry):
    # Windows cloud placeholders can be reparse points without redirecting a name.
    name_surrogate = getattr(entry, "st_reparse_tag", 0) & 0x20000000
    return stat.S_ISLNK(entry.st_mode) or bool(name_surrogate)


def _system_path(path: Path) -> Path:
    # macOS exposes its system temporary directories through these root aliases.
    if sys.platform == "darwin" and path.anchor == "/" and path.parts[1:2] in (("var",), ("tmp",)):
        alias = Path("/") / path.parts[1]
        if alias.is_symlink() and alias.readlink() in (Path("private") / alias.name, Path("/private") / alias.name):
            return Path("/private") / path.relative_to("/")
    return path


class LibraryPathError(OSError):
    """A path does not satisfy the library's ownership or link policy."""


@dataclass(frozen=True)
class StorageSubtree:
    """A fixed child of a configured root. Only the configured root may be linked."""
    parent: Path
    name: str

    def __fspath__(self):
        return os.fspath(Path(self.parent) / self.name)


def _rooted_path(root: Path, path: Path) -> tuple[Path, Path]:
    """Follow the selected root once. Keep every component beneath it lexical."""
    if isinstance(root, StorageSubtree):
        base, candidate = _rooted_path(root.parent, path)
        if not candidate.is_relative_to(base / root.name):
            raise LibraryPathError("The file must be inside the storage folder.")
        return base, candidate
    root = Path(root).absolute()
    path = Path(path)
    if os.name == "nt" and any(":" in part for part in path.parts[1:]):
        raise LibraryPathError("Choose a regular file.")
    if not path.is_absolute() or ".." in path.parts:
        raise LibraryPathError("The file must be inside the library.")
    target = root.resolve()
    if path.is_relative_to(root):
        return target, _system_path(target / path.relative_to(root))
    # Some older rows already store the physical spelling of the root.
    if path.is_relative_to(target):
        return target, path
    raise LibraryPathError("The file must be inside the library.")


def checked_path(root: Path, path: Path) -> Path:
    """Check ownership and every component strictly inside the chosen root."""
    selected = Path(root).absolute()
    original = Path(path)
    root, path = _rooted_path(root, path)
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        try:
            entry = current.lstat()
        except FileNotFoundError:
            break
        if _redirected(entry):
            raise LibraryPathError("The library path contains a link.")
    if not path.resolve().is_relative_to(root.resolve()):
        raise LibraryPathError("The file must be inside the library.")
    # Keep the configured spelling for paths returned to the UI and index.
    if original.is_relative_to(selected):
        return original
    return selected / path.relative_to(selected.resolve())


@contextmanager
def _parent_directory(root: Path, path: Path, *, create: bool = False):
    """Hold each directory against replacement, or use directory-relative I/O."""
    root = Path(root).absolute()
    checked_path(root, path)
    root, path = _system_path(root), _system_path(path)
    if create:
        root.mkdir(parents=True, exist_ok=True)
    with ExitStack() as held:
        directory = root
        parent_fd = None
        for part in ("", *path.parent.relative_to(root).parts):
            directory /= part
            if part and create:
                try:
                    if os.name == "nt":
                        directory.mkdir()
                    else:
                        os.mkdir(part, dir_fd=parent_fd)
                except FileExistsError:
                    pass
            if os.name == "nt":
                import _winapi
                # Open the directory itself and deny renaming until publication.
                handle = _winapi.CreateFile(str(directory), 0, 3, 0, 3, 0x02200000, 0)
                held.callback(_winapi.CloseHandle, handle)
                if _redirected(directory.lstat()):
                    raise OSError("The library path contains a link.")
            else:
                flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                parent_fd = os.open(part or root, flags, dir_fd=parent_fd)
                held.callback(os.close, parent_fd)
        yield parent_fd


def ensure_parent(root, path):
    base, target = _rooted_path(root, path)
    with _parent_directory(base, target, create=True):
        pass


@contextmanager
def pinned_parent(root, path, *, create=False):
    """Keep a directory stable for a producer which needs to operate by name."""
    base, target = _rooted_path(root, path)
    with _parent_directory(base, target, create=create) as fd:
        if fd is None:
            yield target.parent
        else:
            # Both Linux and macOS expose held directory descriptors here.
            directory = Path("/dev/fd") / str(fd)
            if not os.path.samestat(directory.stat(), os.fstat(fd)):
                raise LibraryPathError("The settings folder changed.")
            yield directory


def _check_opened(root, path, fd):
    path = checked_path(root, path)
    opened = os.fstat(fd)
    if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
            or not os.path.samestat(opened, path.stat())):
        raise OSError("Could not verify the opened file.")


@contextmanager
def open_regular(root, path, *, binary=False, newline=None):
    root, path = _rooted_path(root, path)
    with _parent_directory(root, path) as parent:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
        if not stat.S_ISREG(path.lstat().st_mode):
            raise OSError("Choose a regular file.")
        fd = os.open(path if parent is None else path.name, flags, dir_fd=parent)
        with os.fdopen(fd, "rb" if binary else "r", encoding=None if binary else "utf-8", newline=newline) as stream:
            _check_opened(root, path, fd)
            yield stream


def read_checked_bytes(root, path, *, limit=None):
    with open_regular(root, path, binary=True) as stream:
        data = stream.read() if limit is None else stream.read(limit + 1)
    if limit is not None and len(data) > limit:
        raise ValueError("The saved file exceeds the size limit.")
    return data


def read_checked_json(root, path):
    # Large transcripts can contain word timings. Bound the raw bytes before parsing.
    return json.loads(read_checked_bytes(root, path, limit=64 * 1024 * 1024).decode("utf-8"))


def unlink_regular(root, path):
    root, path = _rooted_path(root, path)
    with _parent_directory(root, path) as parent:
        if not stat.S_ISREG(path.lstat().st_mode):
            raise LibraryPathError("Choose a regular file.")
        os.unlink(path if parent is None else path.name, dir_fd=parent)


def normalize_export_comments(path: Path, text: str, *, root=None) -> str:
    if _PENDING_COMMENT not in text:
        return text
    sidecar = path.parent / (path.parent.name + ".json")
    try:
        with open_regular(root or Path(path.anchor), sidecar) as source:
            metadata = json.load(source)
    except (OSError, ValueError):
        return text
    if (isinstance(metadata, dict) and metadata.get("long_video_mode") == "lite"
            and metadata.get("comments_status") == "skipped"):
        for newline in ("\n", "\r\n"):
            old = newline.join((COMMENTS_START_MARK, _PENDING_COMMENT, COMMENTS_END_MARK))
            if old in text:
                return text.replace(old, old.replace(_PENDING_COMMENT, _LITE_COMMENT), 1)
    return text


def read_export_markdown(path: Path, *, root=None) -> str:
    from moments import export_links
    with open_regular(root or Path(path.absolute().anchor), path) as source:
        return export_links(normalize_export_comments(path, source.read(), root=root))


@contextmanager
def atomic_output(path: Path, *, root=None, encoding=None, newline=None, mode=0o666):
    path = Path(path).absolute()
    root, path = _rooted_path(root or path.anchor, path)
    with _parent_directory(root, path, create=True) as parent:
        tmp = path.with_name(f".{uuid.uuid4().hex}.tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        fd = os.open(tmp if parent is None else tmp.name, flags, mode, dir_fd=parent)
        published = False
        identity = os.fstat(fd)
        try:
            with os.fdopen(fd, "w" if encoding else "wb", encoding=encoding, newline=newline) as stream:
                _check_opened(root, tmp, fd)
                yield stream
            for delay in (0.05, 0.2, 0.5, None):
                try:
                    checked_path(root, path)
                    if not os.path.samestat(identity, tmp.lstat()):
                        raise OSError("The temporary file changed before it was saved.")
                    if parent is None:
                        tmp.replace(path)
                    else:
                        os.replace(tmp.name, path.name, src_dir_fd=parent, dst_dir_fd=parent)
                    published = True
                    break
                except PermissionError:
                    if delay is None:
                        raise
                    time.sleep(delay)
        finally:
            if not published:
                try:
                    if os.path.samestat(identity, tmp.lstat()):
                        if parent is None:
                            tmp.unlink()
                        else:
                            os.unlink(tmp.name, dir_fd=parent)
                except OSError:
                    pass


def _atomic_write_text(path: Path, text: str, *, encoding="utf-8", newline=None, root=None) -> None:
    with atomic_output(path, root=root, encoding=encoding, newline=newline) as stream:
        stream.write(text)


def _is_writable_dir(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    probe = path / f".yoink-write-test-{os.getpid()}-{uuid.uuid4().hex}.tmp"
    try:
        root, probe = _rooted_path(path, probe.absolute())
        with _parent_directory(root, probe) as parent:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            name = probe if parent is None else probe.name
            fd = os.open(name, flags, 0o600, dir_fd=parent)
            identity = os.fstat(fd)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(b"ok")
            finally:
                if os.path.samestat(identity, probe.lstat()):
                    os.unlink(name, dir_fd=parent)
        return True
    except OSError:
        return False


def move_library_folder(root: Path, source: Path, destination: Path) -> None:
    """Pin both parents through the final checks and the same-volume rename."""
    target_root, source = _rooted_path(root, source)
    destination = target_root / checked_path(root, destination).relative_to(root)
    with _parent_directory(target_root, source) as src_parent:
        with _parent_directory(target_root, destination, create=True) as dst_parent:
            checked_path(target_root, source)
            if checked_path(target_root, destination).exists():
                raise FileExistsError("The destination is occupied.")
            if dst_parent is None:
                source.rename(destination)
            else:
                os.rename(source.name, destination.name, src_dir_fd=src_parent, dst_dir_fd=dst_parent)


def _topic_folder_name(topic: str) -> str:
    cleaned = _FORBIDDEN_PATH_CHARS.sub("", topic).strip().rstrip(".")
    return cleaned or "Uncategorized"


def _path_under_any(resolved: Path, roots: set[Path]) -> bool:
    for root in roots:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False
