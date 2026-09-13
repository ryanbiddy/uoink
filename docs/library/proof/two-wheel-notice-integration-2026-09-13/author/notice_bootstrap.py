"""Fixed isolated pytest entry; copied integrator audit policy, no site startup."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
OVERLAY = HERE / "overlay"
SUPPORT = r"C:\Users\hello\AppData\Roaming\Python\Python314\site-packages"
FORBIDDEN = r"C:\Users\hello\AppData\Local\Uoink\index.db"
assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
assert os.path.normcase(sys.executable) == os.path.normcase(r"C:\Python314\python.exe")
assert os.environ.get("IG_FORBIDDEN_LIVE") == FORBIDDEN


def audit(event, args):
    if event in ('open', 'sqlite3.connect'):
        value = args[0]
        if isinstance(value, (str, bytes, os.PathLike)):
            name = os.fsdecode(value).replace('\\', '/').lower()
            forbidden = os.environ['IG_FORBIDDEN_LIVE'].replace('\\', '/').lower()
            if forbidden in name:
                raise PermissionError('Integrator guard: live index forbidden')
    if event in ('socket.connect', 'socket.bind', 'socket.sendto', 'socket.getaddrinfo'):
        addr = args[:2] if event == 'socket.getaddrinfo' else args[1]
        if isinstance(addr, tuple) and (str(addr[1]) == '5179' or addr[0] not in ('127.0.0.1', '::1', 'localhost', '0.0.0.0', '')):
            raise PermissionError('Integrator guard: external network / 5179 forbidden')
    if event == 'subprocess.Popen':
        cmd = args[1]
        first = cmd[0] if isinstance(cmd, (list, tuple)) and cmd else str(cmd).split()[0]
        name = os.path.basename(str(first)).lower().strip('"')
        if name.split('.')[0] in ('claude', 'codex', 'gemini', 'grok'):
            raise PermissionError('Integrator guard: real model process forbidden')


sys.addaudithook(audit)
assert "pytest" not in sys.modules
initial_path = list(sys.path)
sys.path[:0] = [str(OVERLAY), SUPPORT]
os.environ.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONDONTWRITEBYTECODE="1",
                  PHASE3_REQUIRE_IMPLEMENTATION="1", PY_COLORS="0", NO_COLOR="1")
profile = HERE / "pytest-profile01"
assert profile.is_dir()
for key in ("LOCALAPPDATA", "APPDATA", "XDG_DATA_HOME", "TEMP", "TMP", "UOINK_DATA_ROOT",
            "UOINK_OUTPUT_ROOT", "UOINK_OUTPUT_DIR", "YOINK_OUTPUT_DIR"):
    os.environ[key] = str(profile)
os.environ["UOINK_INDEX_PATH"] = str(profile / "unused-index.db")
saved = OVERLAY / "_scratch"
os.environ["AGW_HEAVY_GUARD_RECEIPT"] = str(saved / "notice01-heavy.json")
os.environ["IG_PARTITION_RECEIPT_PATH"] = str(saved / "notice01-partition")
spec = importlib.util.spec_from_file_location("notice_heavy_guard", saved / "agw_heavy_import_guard.py")
heavy = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = heavy
spec.loader.exec_module(heavy)
assert heavy._finder in sys.meta_path
import pytest

arguments = ["-q", "-ra", "--tb=short", "--color=no", "--runxfail",
             "-p", "no:cacheprovider", "-p", "_scratch.partition_receipt_plugin",
             "-c", str(OVERLAY / "pytest.ini"), "--rootdir=" + str(OVERLAY),
             "--confcutdir=" + str(OVERLAY), "--basetemp=" + str(saved / "notice01-temp"),
             "--junitxml=" + str(saved / "notice01.xml"),
             "tests/test_runtime_setuptools_notices.py", "tests/test_installer_dependency_lock.py",
             "tests/test_c02_reliability_faster_whisper.py", "tests/test_notice_integration.py"]
os.chdir(OVERLAY)
started = time.monotonic()
code = int(pytest.main(arguments, plugins=[heavy]))
receipt = {"entry": "pytest.main(arguments, plugins=[heavy])", "arguments": arguments,
           "pytest_version": pytest.__version__, "pytest_exit": code,
           "elapsed_seconds": time.monotonic() - started, "initial_sys_path": initial_path,
           "added_import_roots": [str(OVERLAY), SUPPORT], "isolated": bool(sys.flags.isolated),
           "no_site": bool(sys.flags.no_site), "no_bytecode": sys.dont_write_bytecode,
           "heavy_guard_present": heavy._finder in sys.meta_path,
           "forbidden_live_binding": os.environ.get("IG_FORBIDDEN_LIVE") == FORBIDDEN,
           "full_build_or_model_execution": False}
with (HERE / "pytest-bootstrap01.json").open("x", encoding="utf8") as output:
    json.dump(receipt, output, indent=2)
raise SystemExit(code)
