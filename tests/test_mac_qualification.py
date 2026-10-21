"""Offline qualification tests. No product imports, pip runs, or downloads."""
from __future__ import annotations

import hashlib
import io
import contextlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import urllib.error
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/mac"))
import qualify_deps as deps
import import_smoke as smoke

FIXTURE = json.loads((ROOT / "tests/fixtures/mac_qualification.json").read_text(encoding="utf-8"))


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="uoink-mac-unit-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.release = json.loads(json.dumps(FIXTURE["release"]))
        self.pins = {"schema_version": 1, "release_tag": self.release["tag_name"], "assets": [
            {"name": row["name"], "size_bytes": 7, "sha256": hashlib.sha256(b"fixture").hexdigest()}
            for row in self.release["assets"][:2]]}
        self.pin_path = self.root / "standalone-python.json"
        deps.write_json(self.pin_path, self.pins)
        pins_patch = patch.object(deps, "STANDALONE_PINS", self.pin_path)
        pins_patch.start()
        self.addCleanup(pins_patch.stop)
        # Small graph fixtures test the resolver independently of the five
        # reviewed UI additions, covered by test_mac_ui and the real manifest.
        ui_patch = patch.object(deps, "ui_pins", return_value={})
        ui_patch.start()
        self.addCleanup(ui_patch.stop)
        # Any accidentally unmocked external work makes the offline test fail.
        self.network = patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden"))
        self.processes = patch("subprocess.run", side_effect=AssertionError("process forbidden"))
        self.network.start()
        self.processes.start()
        self.addCleanup(self.network.stop)
        self.addCleanup(self.processes.stop)

    def test_every_pin_and_platform_survive_a_missing_wheel(self):
        lock = self.root / "lock.txt"
        lock.write_text("# fixture\n" + "\n".join(FIXTURE["pins"]), encoding="utf-8")
        exclusions = self.root / "exclude.json"
        deps.write_json(exclusions, FIXTURE["exclusions"])
        commands = []

        def fake_run(command, log, timeout=240):
            commands.append(command)
            self.assertIn("--only-binary=:all:", command)
            self.assertEqual(command[command.index("--python-version") + 1], "3.13")
            self.assertEqual(command[command.index("--implementation") + 1], "cp")
            if "-r" in command:
                self.assertNotIn("--no-deps", command)
                return 1
            pin = command[-1]
            self.assertIn("--no-deps", command)
            if pin not in FIXTURE["wheel_names"]:
                return 1
            destination = Path(command[command.index("--dest") + 1])
            (destination / FIXTURE["wheel_names"][pin]).write_bytes(b"fixture wheel")
            return 0

        output = self.root / "evidence"
        with patch.object(deps, "run_logged", side_effect=fake_run):
            report = deps.qualify_wheels(lock, exclusions, output)
        self.assertEqual(len(commands), 8)  # Three pins and one graph per target.
        self.assertEqual(len(report["packages"]), 6)
        for platform in deps.PLATFORMS:
            rows = [row for row in report["packages"] if row["platform"] == platform]
            self.assertEqual([row["wheel_found"] for row in rows], [True, False, True])
            self.assertEqual(rows[0]["wheels"][0]["minimum_macos_implied"], "14.0")
            self.assertIsNone(rows[2]["wheels"][0]["minimum_macos_implied"])
        self.assertEqual(len(list((output / "wheels").glob("*.whl"))), 2)
        self.assertEqual(report["exclusions"][0]["package"], "pywin32")
        self.assertFalse(any(row["resolved"] for row in report["graph_attempts"]))
        self.assertEqual(json.loads((output / "wheels.json").read_text()), report)

    def test_lock_parser_fails_closed(self):
        lock = self.root / "lock.txt"
        for text in ("one>=1", "one==*", "one==1; sys_platform == 'darwin'", "one==1\none==2",
                     "clr_loader==1\nclr-loader==1", "--extra-index-url https://example.invalid"):
            with self.subTest(text=text):
                lock.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    deps.read_pins(lock)

    def test_wheel_tags_are_lower_bounds_not_runtime_claims(self):
        universal = deps.wheel_details("sample-1.0-2-cp313-abi3-macosx_10_9_universal2.whl")
        self.assertEqual(universal["minimum_macos_implied"], "11.0")
        compound = deps.wheel_details("sample-1.0-cp313-cp313-macosx_15_0_arm64.macosx_14_0_arm64.whl")
        self.assertEqual(compound["minimum_macos_implied"], "14.0")
        self.assertIn("not Mach-O", compound["minimum_macos_basis"])
        self.assertIsNone(deps.wheel_details("sample-1.0-py3-none-any.whl")["minimum_macos_implied"])

    def test_bad_wheel_does_not_hide_later_wheels(self):
        source, destination = self.root / "source", self.root / "destination"
        source.mkdir()
        destination.mkdir()
        (source / "bad.whl").write_bytes(b"broken")
        (source / "valid-1.0.0-py3-none-any.whl").write_bytes(b"valid")
        found, errors = deps.collect_wheels(source, destination)
        self.assertEqual(found[0]["version"], "1.0.0")
        self.assertEqual(errors[0]["filename"], "bad.whl")
        self.assertTrue((destination / found[0]["filename"]).is_file())

    def test_standalone_selection_and_download_hashes(self):
        release = self.release
        self.assertEqual(len(deps.standalone_candidates(release, self.pins)), 2)

        def fake_request(url):
            return io.BytesIO(json.dumps(release).encode() if url == deps.RELEASE_API + self.pins["release_tag"] else b"fixture")

        with patch.object(deps, "request", side_effect=fake_request):
            report = deps.qualify_standalone(self.root / "standalone")
        self.assertEqual(len(report["candidates"]), 2)
        for row in report["candidates"]:
            self.assertTrue(row["downloaded"])
            self.assertEqual(row["size_bytes"], 7)
            self.assertEqual(row["sha256"], hashlib.sha256(b"fixture").hexdigest())
        self.assertEqual(list((self.root / "standalone").glob("*.tar.gz")), [])

    def test_standalone_failure_is_recorded_and_next_candidate_runs(self):
        def fake_request(url):
            if url == deps.RELEASE_API + self.pins["release_tag"]:
                return io.BytesIO(json.dumps(self.release).encode())
            return io.BytesIO(b"short" if url.endswith("install_only.tar.gz") else b"fixture")

        with patch.object(deps, "request", side_effect=fake_request):
            report = deps.qualify_standalone(self.root / "standalone")
        self.assertEqual([row["downloaded"] for row in report["candidates"]], [False, True])
        self.assertIn("size differs", report["candidates"][0]["error"])

    def test_no_candidate_is_an_explicit_failure(self):
        self.release["assets"] = []
        with patch.object(deps, "request", return_value=io.BytesIO(
                json.dumps(self.release).encode())):
            report = deps.qualify_standalone(self.root / "standalone")
        self.assertIn("matching pinned asset", report["error"])

    def test_standalone_rejects_changed_bytes_without_published_digest(self):
        def fake_request(url):
            if url.startswith(deps.RELEASE_API):
                return io.BytesIO(json.dumps(self.release).encode())
            return io.BytesIO(b"changed")  # Same length; only the pinned hash catches this.
        with patch.object(deps, "request", side_effect=fake_request):
            report = deps.qualify_standalone(self.root / "standalone")
        self.assertTrue(all(not row["downloaded"] for row in report["candidates"]))
        self.assertIn("pinned SHA-256", report["candidates"][0]["error"])

    def test_standalone_rejects_changed_release_and_unpinned_assets(self):
        self.release["tag_name"] = "20261002"
        with self.assertRaisesRegex(ValueError, "Release tag differs"):
            deps.standalone_candidates(self.release, self.pins)
        self.pins["assets"][0]["sha256"] = ""
        deps.write_json(self.pin_path, self.pins)
        with patch.object(deps, "request") as network:
            report = deps.qualify_standalone(self.root / "standalone")
        network.assert_not_called()
        self.assertIn("asset pin", report["error"])

    def test_standalone_http_status_is_reported_on_console_and_disk(self):
        output = io.StringIO()
        error = urllib.error.HTTPError("https://api.github.com/fixture", 403, "rate limit exceeded", {}, None)
        with patch.object(deps, "request", side_effect=error), contextlib.redirect_stdout(output):
            report = deps.qualify_standalone(self.root / "standalone")
        self.assertEqual(report["http_status"], 403)
        self.assertIn("403", output.getvalue())
        self.assertEqual(json.loads((self.root / "standalone/python-standalone.json").read_text())["http_status"], 403)

    def test_github_token_is_only_sent_to_api(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "fixture-only"}), \
                patch.object(deps.urllib.request, "urlopen", return_value=io.BytesIO()) as opened:
            for url, authorized in ((deps.RELEASE_API + self.pins["release_tag"], True),
                                    ("https://github.com/fixture.tar.gz", False),
                                    ("https://files.pythonhosted.org/fixture.tar.gz", False)):
                deps.request(url)
                request = opened.call_args.args[0]
                self.assertEqual(request.get_header("Authorization") is not None, authorized)

    def test_build_tooling_is_exact_hashed_and_matches_windows_versions(self):
        lines = [line for line in deps.BUILD_TOOLING.read_text().splitlines() if line and not line.startswith("#")]
        expected = {name: deps.windows_build_pin(key) for name, key in (
            ("pip", "PIP_VERSION"), ("setuptools", "SETUPTOOLS_VERSION"),
            ("wheel", "WHEEL_VERSION"), ("packaging", "PACKAGING_VERSION"))}
        self.assertEqual(len(lines), len(expected))
        for line in lines:
            pin, digest = line.split(" --hash=sha256:")
            name, version = pin.split("==")
            self.assertEqual(version, expected.pop(name))
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertFalse(expected)

    def test_recursive_startup_discovery_does_not_execute_modules(self):
        (self.root / "entry.py").write_text(
            "import second\ntry:\n import optional\nexcept ImportError:\n pass\n"
            "def lazy():\n import lazy_only\nraise RuntimeError('never execute')\n", encoding="utf-8")
        (self.root / "second.py").write_text("from package import child\n", encoding="utf-8")
        for name in ("optional", "lazy_only"):
            (self.root / f"{name}.py").write_text("", encoding="utf-8")
        (self.root / "package").mkdir()
        (self.root / "package/__init__.py").write_text("from . import child\n", encoding="utf-8")
        (self.root / "package/child.py").write_text("import entry\n", encoding="utf-8")
        self.assertEqual(smoke.startup_modules(self.root, ("entry",)),
                         ["entry", "lazy_only", "optional", "package", "package.child", "second"])

    def test_smoke_selects_one_wheel_per_distribution(self):
        for name in ("sample-1-cp313-cp313-macosx_15_0_arm64.whl",
                     "sample-1-cp313-cp313-macosx_14_0_arm64.whl", "other-2-py3-none-any.whl"):
            (self.root / name).write_bytes(b"")
        selected = smoke.select_wheels(self.root)
        self.assertEqual(len(selected), 2)
        self.assertTrue(any("macosx_14_0_arm64" in path.name for path in selected))

    def test_pinned_sdist_verified_before_build_and_recorded(self):
        body = b"reviewed source fixture"
        pin = {"version": "0.1.0", "url": "https://example.invalid/proxy_tools-0.1.0.tar.gz",
               "blake2b_256": hashlib.blake2b(body, digest_size=32).hexdigest()}
        manifest = self.root / "sources.json"
        deps.write_json(manifest, {"proxy-tools": pin})
        commands = []
        wheels = self.root / "wheels"
        wheels.mkdir()

        def fake_run(command, log, timeout=240):
            commands.append(command)
            if "wheel" in command:
                self.assertIn("--no-deps", command)
                self.assertIn("--no-build-isolation", command)
                self.assertIn("--no-index", command)
                self.assertEqual(Path(command[-1]).read_bytes(), body)
                destination = Path(command[command.index("--wheel-dir") + 1])
                (destination / "proxy_tools-0.1.0-py2.py3-none-any.whl").write_bytes(b"built fixture")
            return 0

        with patch.object(deps, "SOURCE_PINS", manifest), patch.object(deps, "run_logged", side_effect=fake_run), \
                patch.object(deps, "request", return_value=io.BytesIO(body)):
            report = deps.build_source_wheels([("proxy_tools", "0.1.0")], wheels, self.root)
        row = report["proxy-tools"]
        self.assertTrue(row["wheel_found"])
        self.assertEqual(row["source_sha256"], hashlib.sha256(body).hexdigest())
        self.assertEqual(row["source_blake2b_256"], pin["blake2b_256"])
        self.assertEqual(len(commands), 2)
        self.assertIn("--require-hashes", commands[0])
        self.assertIn(str(deps.BUILD_TOOLING), commands[0])

        # Wrong bytes at the exact pinned URL never reach pip's build hooks.
        commands.clear()
        with patch.object(deps, "SOURCE_PINS", manifest), patch.object(deps, "run_logged", side_effect=fake_run), \
                patch.object(deps, "request", return_value=io.BytesIO(body + b"tamper")):
            report = deps.build_source_wheels([("proxy_tools", "0.1.0")], wheels, self.root)
        self.assertFalse(report["proxy-tools"]["wheel_found"])
        self.assertIn("BLAKE2-256 mismatch", str(report))
        self.assertEqual(len(commands), 1)

    def test_source_content_addresses_match_retained_qualification_urls(self):
        pins = json.loads(deps.SOURCE_PINS.read_text(encoding="utf-8"))
        retained = (ROOT / "docs/library/GEMINI-PYTHON-313-QUALIFICATION-2026-09-09.md").read_text(encoding="utf-8")
        for row in pins.values():
            self.assertIn(row["url"], retained)
            address = "".join(row["url"].split("/packages/", 1)[1].split("/")[:3])
            self.assertEqual(row["blake2b_256"], address)
            self.assertEqual(len(address), 64)

    def test_nltk_uses_existing_builder_and_rejects_non_windows_output_hash(self):
        wheels = self.root / "wheels"
        wheels.mkdir()
        commands, builds = [], []
        class Builder:
            EXPECTED_WHEEL_NAME = "nltk-3.10.3-py3-none-any.whl"
            EXPECTED_WHEEL_SHA256 = "f" * 64
            OUTPUT_WHEEL_NAME = "nltk-3.10.3+uoink.pathsec1-py3-none-any.whl"
            @staticmethod
            def build_nltk_wheel(source, output):
                builds.append((source, output))
                output.mkdir()
                (output / Builder.OUTPUT_WHEEL_NAME).write_bytes(b"wrong output hash")
                return {}
        loader = SimpleNamespace(exec_module=lambda module: None)
        def fake_run(command, log, timeout=240):
            commands.append(command)
            if "download" in command:
                self.assertIn("--require-hashes", command)
                self.assertIn(Builder.EXPECTED_WHEEL_SHA256, Path(command[-1]).read_text())
            return 0
        with patch.object(deps.importlib.util, "spec_from_file_location", return_value=SimpleNamespace(loader=loader)), \
                patch.object(deps.importlib.util, "module_from_spec", return_value=Builder), \
                patch.object(deps, "run_logged", side_effect=fake_run):
            report = deps.build_source_wheels([("nltk", "3.10.3+uoink.pathsec1")], wheels, self.root)
        self.assertEqual(len(builds), 1)
        self.assertFalse(report["nltk"]["wheel_found"])
        self.assertIn("Windows build hash", str(report))
        self.assertEqual(list(wheels.iterdir()), [])

    def test_combined_resolver_uses_built_wheels(self):
        lock = self.root / "lock.txt"
        lock.write_text("proxy_tools==0.1.0\n", encoding="utf-8")
        exclusions = self.root / "exclude.json"
        deps.write_json(exclusions, {})
        commands = []
        def fake_run(command, log, timeout=240):
            commands.append(command)
            self.assertIn("--find-links", command)
            self.assertIn("-r", command)
            destination = Path(command[command.index("--dest") + 1])
            (destination / "proxy_tools-0.1.0-py3-none-any.whl").write_bytes(b"fixture wheel")
            return 0
        built = {"proxy-tools": {"package": "proxy-tools", "version": "0.1.0",
                                 "wheel_found": True, "wheels": [], "errors": []}}
        with patch.object(deps, "build_source_wheels", return_value=built), \
                patch.object(deps, "run_logged", side_effect=fake_run):
            report = deps.qualify_wheels(lock, exclusions, self.root / "evidence")
        self.assertEqual(len(commands), 2)
        self.assertTrue(all(row["source_built"] for row in report["packages"]))

    def test_smoke_rejects_missing_pins_and_changed_bytes(self):
        wheel = self.root / "sample-1.0-py3-none-any.whl"
        wheel.write_bytes(b"fixture")
        manifest = {"pins": [{"package": "sample", "version": "1.0.0"}], "errors": [],
                    "wheels": [{"filename": wheel.name, "sha256": deps.sha256(wheel)}]}
        deps.write_json(self.root / "wheel-manifest.json", manifest)
        with patch.dict(sys.modules, {"pip": None}):
            self.assertEqual(smoke.verify_complete_set(self.root, [wheel]), [])
        self.assertIn("Missing qualified pin", str(smoke.verify_complete_set(self.root, [])))
        wheel.write_bytes(b"changed")
        self.assertIn("hash mismatch", str(smoke.verify_complete_set(self.root, [wheel])))


if __name__ == "__main__":
    unittest.main()
