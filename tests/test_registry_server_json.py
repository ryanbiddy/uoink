"""server.json (official MCP registry listing) stays tied to the release."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_registry_server_json", ROOT / "scripts" / "check_registry_server_json.py")
check_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_module)

SHA = "a" * 64


def _write(tmp_path, version, sha=SHA, url=None, name="io.github.ryanbiddy/uoink"):
    data = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    data["name"] = name
    data["version"] = version
    pkg = data["packages"][0]
    pkg["identifier"] = url or (
        f"https://github.com/ryanbiddy/uoink/releases/download/v{version}/uoink-{version}.mcpb")
    pkg["fileSha256"] = sha
    (tmp_path / "server.json").write_text(json.dumps(data), encoding="utf-8")
    (tmp_path / "VERSION").write_text(version + "\n", encoding="utf-8")
    return tmp_path / "server.json"


def test_repo_server_json_tracks_version_file():
    data = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert data["version"] == version
    assert data["packages"][0]["identifier"].endswith(f"/v{version}/uoink-{version}.mcpb")
    assert 1 <= len(data["description"]) <= 100


def test_matching_listing_passes(tmp_path):
    path = _write(tmp_path, "3.9.3")
    sums = tmp_path / "SHA256SUMS.txt"
    sums.write_text(f"{SHA}  uoink-3.9.3.mcpb\n{'b' * 64}  Uoink-Setup-3.9.3.exe\n", encoding="utf-8")
    assert check_module.check(path, "v3.9.3", sums) == []


def test_mismatches_fail_closed(tmp_path):
    path = _write(tmp_path, "3.9.3", sha="<sha256 pending>")
    errors = check_module.check(path, "v3.9.4", None)
    assert any("version" in e for e in errors)
    assert any("fileSha256" in e for e in errors)
    sums = tmp_path / "SHA256SUMS.txt"
    sums.write_text(f"{'c' * 64}  uoink-3.9.3.mcpb\n", encoding="utf-8")
    path = _write(tmp_path, "3.9.3")
    assert any("SHA256SUMS" in e for e in check_module.check(path, "v3.9.3", sums))
    path = _write(tmp_path, "3.9.3", url="https://example.com/uoink-3.9.3.mcpb")
    assert any("identifier" in e for e in check_module.check(path, "v3.9.3", None))
    path = _write(tmp_path, "3.9.3", name="io.github.someone/uoink")
    assert any("name" in e for e in check_module.check(path, "v3.9.3", None))
