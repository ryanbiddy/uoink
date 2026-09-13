"""Extra scratch regressions; no imports, loader, filesystem paths or entry point."""


def register(scope):
    resolver = scope["resolver"]
    fixture, refuse, patched = scope["fixture"], scope["refuse"], scope["patched"]
    altered, case = scope["altered_stat"], scope["case"]
    os, Path = scope["os"], scope["Path"]
    types, ast = scope["types"], scope["ast"]
    assert os.name == "nt", "This identity regression qualification is explicitly Windows"

    @case("identity_original_73_assertions_unchanged")
    def original_assertions():
        current = ast.parse(scope["RAW"]["qualify_resolver.py"])
        original = ast.parse(scope["RAW"]["original73-harness.py"])
        def functions(tree):
            return {node.name: ast.dump(node, include_attributes=False)
                    for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        old, new = functions(original), functions(current)
        assert set(old) == set(new)
        assert {name for name in old if old[name] != new[name]} == {"altered_stat"}
        def loops(tree):
            return [ast.dump(node, include_attributes=False) for node in tree.body
                    if isinstance(node, ast.For)]
        assert loops(original) == loops(current)
        assert scope["ORIGINAL_CASES"] == tuple(name for name, _ in scope["CASES"][:73])

    @case("identity_stable_cross_api_ctime_difference_is_recorded")
    def stable_namespace_difference():
        trusted, root, snapshot = fixture("identity-stable-ctime")
        original_fstat = os.fstat
        def changed_namespace(fd):
            observed = original_fstat(fd)
            return altered(observed, st_ctime_ns=observed.st_ctime_ns + 1234567)
        with patched(os, "fstat", changed_namespace):
            admitted = resolver.admit_snapshot(trusted, "tiny", root, snapshot)
            binding = resolver.bind_for_constructor(admitted)
        assert binding.local_files_only is True and binding.real_runtime_approved is False
        assert all(item.identity[6] != item.handle_identity[6] for item in binding.files)
        assert all(item.identity[:6] == item.handle_identity[:6] and item.identity[7] == item.handle_identity[7] for item in binding.files)

    for location in ("path", "handle"):
        @case("identity_windows_birthtime_absent_" + location)
        def absent_birthtime(location=location):
            trusted, root, snapshot = fixture("identity-absent-birth-" + location)
            if location == "path":
                original = Path.lstat
                def missing(path, *args, **kwargs):
                    observed = original(path, *args, **kwargs)
                    if path == snapshot / "config.json":
                        observed = altered(observed)
                        del observed.st_birthtime_ns
                    return observed
                with patched(Path, "lstat", missing):
                    refuse(lambda: resolver.admit_snapshot(trusted, "tiny", root, snapshot), "Required Windows birthtime unavailable")
            else:
                original = os.fstat
                def missing(fd):
                    observed = altered(original(fd))
                    del observed.st_birthtime_ns
                    return observed
                with patched(os, "fstat", missing):
                    refuse(lambda: resolver.admit_snapshot(trusted, "tiny", root, snapshot), "Required Windows birthtime unavailable")

    @case("identity_windows_birthtime_boolean_refused")
    def birth_boolean():
        fake = types.SimpleNamespace(st_birthtime_ns=True)
        refuse(lambda: resolver._cross_api_identity(fake), "Required Windows birthtime unavailable")

    @case("identity_cross_api_birthtime_changed")
    def cross_birthtime():
        trusted, root, snapshot = fixture("identity-cross-birth")
        original = os.fstat
        def different(fd):
            observed = original(fd)
            return altered(observed, st_birthtime_ns=observed.st_birthtime_ns + 1)
        with patched(os, "fstat", different):
            refuse(lambda: resolver.admit_snapshot(trusted, "tiny", root, snapshot), "Asset changed before open")

    for field in ("st_ctime_ns", "st_birthtime_ns"):
        @case("identity_same_handle_change_" + field)
        def same_handle(field=field):
            trusted, root, snapshot = fixture("identity-handle-" + field.replace("_", "-"))
            original, calls = os.fstat, [0]
            def change(fd):
                observed = original(fd)
                calls[0] += 1
                return altered(observed, **{field: getattr(observed, field) + 1}) if calls[0] == 2 else observed
            with patched(os, "fstat", change):
                refuse(lambda: resolver.admit_snapshot(trusted, "tiny", root, snapshot), "Asset changed during read")
            assert calls[0] == 2

        @case("identity_same_path_change_" + field)
        def same_path(field=field):
            trusted, root, snapshot = fixture("identity-path-" + field.replace("_", "-"))
            original, calls = resolver._checked_chain, [0]
            def change(path, **kwargs):
                observed = original(path, **kwargs)
                if path == snapshot / "config.json":
                    calls[0] += 1
                    if calls[0] == 2:
                        return altered(observed, **{field: getattr(observed, field) + 1})
                return observed
            with patched(resolver, "_checked_chain", change):
                refuse(lambda: resolver.admit_snapshot(trusted, "tiny", root, snapshot), "Asset replaced after read")
            assert calls[0] == 2

    for location in ("path", "handle"):
        @case("identity_ctime_changed_between_admission_and_rebind_" + location)
        def changed_between(location=location):
            trusted, root, snapshot = fixture("identity-rebind-ctime-" + location)
            admitted = resolver.admit_snapshot(trusted, "tiny", root, snapshot)
            if location == "path":
                original = Path.lstat
                def change(path, *args, **kwargs):
                    observed = original(path, *args, **kwargs)
                    return altered(observed, st_ctime_ns=observed.st_ctime_ns + 1) if path == snapshot / "config.json" else observed
                with patched(Path, "lstat", change):
                    refuse(lambda: resolver.bind_for_constructor(admitted), "Snapshot identity changed since admission")
            else:
                original = os.fstat
                def change(fd):
                    observed = original(fd)
                    return altered(observed, st_ctime_ns=observed.st_ctime_ns + 1)
                with patched(os, "fstat", change):
                    refuse(lambda: resolver.bind_for_constructor(admitted), "Snapshot identity changed since admission")

    @case("identity_birthtime_changed_between_admission_and_rebind")
    def birth_changed_between():
        trusted, root, snapshot = fixture("identity-rebind-birth")
        admitted = resolver.admit_snapshot(trusted, "tiny", root, snapshot)
        original_lstat, original_fstat = Path.lstat, os.fstat
        selected_ino = (snapshot / "config.json").lstat().st_ino
        def change_path(path, *args, **kwargs):
            observed = original_lstat(path, *args, **kwargs)
            return altered(observed, st_birthtime_ns=observed.st_birthtime_ns + 1) if path == snapshot / "config.json" else observed
        def change_handle(fd):
            observed = original_fstat(fd)
            return altered(observed, st_birthtime_ns=observed.st_birthtime_ns + 1) if observed.st_ino == selected_ino else observed
        with patched(Path, "lstat", change_path), patched(os, "fstat", change_handle):
            refuse(lambda: resolver.bind_for_constructor(admitted), "Snapshot identity changed since admission")

    @case("identity_non_windows_retains_exact_ctime")
    def non_windows():
        fake = types.SimpleNamespace(st_dev=1, st_ino=2, st_mode=3, st_nlink=1,
                                     st_size=59, st_mtime_ns=100, st_ctime_ns=101)
        changed = types.SimpleNamespace(**vars(fake))
        changed.st_ctime_ns += 1
        with patched(os, "name", "posix"):
            assert resolver._cross_api_identity(fake) != resolver._cross_api_identity(changed)
            assert resolver._cross_api_identity(fake) == resolver._identity(fake)
