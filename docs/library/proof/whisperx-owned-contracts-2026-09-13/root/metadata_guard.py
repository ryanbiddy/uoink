"""Scoped metadata instrumentation for this inert qualification only."""
import os
from pathlib import Path
import stat


def install(base, source_files, run, setup_files, violations):
    original = {"stat": os.stat, "lstat": os.lstat, "readlink": os.readlink,
                "scandir": os.scandir, "listdir": os.listdir,
                "realpath": os.path.realpath, "resolve": Path.resolve}
    abspath, normcase, fspath = os.path.abspath, os.path.normcase, os.fspath
    def lexical(value):
        if not isinstance(value, (str, bytes, os.PathLike)):
            raise PermissionError("File-descriptor metadata is outside scope")
        return normcase(abspath(os.fsdecode(fspath(value))))
    base_name, run_name = lexical(base), lexical(run)
    source_names = {lexical(p) for p in source_files}
    setup_names = {lexical(p) for p in setup_files}
    ancestors = set()
    for name in source_names | setup_names | {run_name}:
        ancestors.update(lexical(p) for p in Path(name).parents)
    state = {"phase": "setup", "metadata_calls": 0}
    def generated(name):
        if name == run_name:
            return True
        if not name.startswith(run_name + os.sep):
            return False
        relative = os.path.relpath(name, run_name)
        # Known receipts plus one generated text fixture; no arbitrary tree.
        return relative in {"generated", "generated" + os.sep + "owned-text-only.txt", "tests.log", "result.json"}
    def reject(event, value):
        violations.append({"event": event, "path": str(value), "phase": state["phase"]})
        raise PermissionError("Metadata outside fixed text/setup/generated scope")
    def allowed(value, *, event="metadata", enumerate_dir=False):
        try:
            name = lexical(value)
        except Exception:
            reject(event, value)
        permitted = generated(name) or name in source_names or name in ancestors
        if state["phase"] == "setup":
            permitted = permitted or name in setup_names
        if enumerate_dir:
            permitted = name == run_name + os.sep + "generated"
        if not permitted:
            reject(event, value)
        return name
    def check_chain(name):
        # No realpath operation can follow a reparse component before checking
        # its lexical chain. Missing leaves are allowed only in fresh output.
        for component in reversed((Path(name),) + tuple(Path(name).parents)):
            item_name = lexical(component)
            if item_name not in ancestors and item_name != name and not generated(item_name):
                reject("ancestor", item_name)
            try:
                info = original["lstat"](item_name)
            except FileNotFoundError:
                if generated(item_name):
                    continue
                raise
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                reject("reparse", item_name)
            if item_name != name and not stat.S_ISDIR(info.st_mode):
                reject("ancestor-type", item_name)
    def wrap(name):
        def guarded(path, *args, **kwargs):
            target = allowed(path, event="os." + name, enumerate_dir=name in {"scandir", "listdir"})
            if kwargs.get("dir_fd") is not None:
                reject("dir-fd", path)
            check_chain(target)
            state["metadata_calls"] += 1
            return original[name](path, *args, **kwargs)
        return guarded
    wrappers = {n: wrap(n) for n in ("stat", "lstat", "readlink", "scandir", "listdir", "realpath")}
    def resolve(path, strict=False):
        target = allowed(path, event="Path.resolve")
        check_chain(target)
        state["metadata_calls"] += 1
        return original["resolve"](path, strict=strict)
    wrappers["resolve"] = resolve
    for name in ("stat", "lstat", "readlink", "scandir", "listdir"):
        setattr(os, name, wrappers[name])
    os.path.realpath = wrappers["realpath"]
    Path.resolve = resolve
    def intact():
        return (all(getattr(os, n) is wrappers[n] for n in ("stat", "lstat", "readlink", "scandir", "listdir"))
                and os.path.realpath is wrappers["realpath"] and Path.resolve is resolve)
    def identities():
        result = {}
        for name in sorted(source_names):
            check_chain(name)
            info = original["lstat"](name)
            fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
            value = {f: getattr(info, f) for f in fields}
            if hasattr(info, "st_birthtime_ns"):
                value["st_birthtime_ns"] = info.st_birthtime_ns
            result[os.path.relpath(name, base_name)] = value
        return result
    return {"state": state, "allowed": allowed, "check_chain": check_chain,
            "intact": intact, "identities": identities, "lexical": lexical,
            "generated": generated}
