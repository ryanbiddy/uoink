"""AS-6 fixture-only companion runner. Run one group per interpreter."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[2]
GROUPS = {
    'service': ['tests/test_source_subscriptions_*.py'],
    'dashboard': ['tests/test_dashboard_sources_*.py'],
    'legacy': ['tests/test_auto_uoink_poll.py', 'tests/test_phase0_liveness.py',
               'tests/test_phase0_podcast_repair.py', 'tests/test_podcast_watch.py',
               'tests/test_quiet_notifications.py'],
    'adapter': ['tests/test_library_adapters.py', 'tests/test_phase0_registry_capture.py'],
    'podcast': ['tests/test_podcast_durability.py', 'tests/test_podcast_corpus_bridge.py',
                'tests/test_podcast_background_jobs.py', 'tests/test_podcast_workflow_truth.py',
                'tests/test_podcast_url_validation.py'],
    'packaging': ['tests/test_installer_files_complete.py', 'tests/test_build_guide_accuracy.py'],
    'heartbeat': ['tests/test_heartbeat_semantics.py'],
    'extra': ['tests/test_phase0_cli.py', 'tests/test_phase0_provenance.py',
              'tests/test_phase0_x_full_text.py'],
    'phase4': ['tests/library_work_astra/test_phase4_aw_acceptance.py'],
}
group = sys.argv[1]
scratch = ROOT / '_scratch'
(scratch / 'as6').mkdir(parents=True, exist_ok=True)
fixture = Path(tempfile.mkdtemp(prefix='', dir=scratch)) if group == 'phase4' else Path(
    tempfile.mkdtemp(prefix=f'as6-{group}-', dir=scratch))
for key in ('LOCALAPPDATA', 'APPDATA', 'XDG_DATA_HOME', 'TEMP', 'TMP',
            'UOINK_DATA_ROOT', 'UOINK_OUTPUT_ROOT', 'UOINK_OUTPUT_DIR', 'YOINK_OUTPUT_DIR'):
    os.environ[key] = str(fixture)
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
os.environ['PHASE3_REQUIRE_IMPLEMENTATION'] = '1'
sys.dont_write_bytecode = True
tempfile.tempdir = str(fixture)
sys.path.insert(0, str(ROOT))
server_copy = fixture / 'helper' / 'server.py'
server_copy.parent.mkdir()
shutil.copyfile(ROOT / 'server.py', server_copy)
assert server_copy.read_bytes() == (ROOT / 'server.py').read_bytes()
attempts = []

def deny(event, detail):
    attempts.append({'event': event, 'detail': str(detail)[:300]})
    if event == 'import':
        raise ImportError('AS6 blocks model imports: ' + str(detail))
    raise AssertionError('AS6 blocked ' + event + ': ' + str(detail))

def check_path(value, event):
    if isinstance(value, int) or value is None:
        return
    if event == 'open' and os.fsdecode(value).lower() in ('nul', '\\\\.\\nul'):
        return
    if not Path(os.fsdecode(value)).resolve().is_relative_to(scratch):
        deny(event, value)

def audit(event, args):
    if event == 'open':
        path, mode, flags = args
        if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)):
            check_path(path, event)
    elif event in ('os.remove', 'os.rmdir', 'os.mkdir', 'os.chmod', 'os.utime'):
        check_path(args[0], event)
    elif event in ('os.rename', 'os.link', 'os.symlink'):
        check_path(args[0], event)
        check_path(args[1], event)
    elif event == 'sqlite3.connect':
        name = os.fsdecode(args[0])
        if name != ':memory:':
            if name.startswith('file:'):
                from urllib.parse import unquote
                name = unquote(name[5:].split('?', 1)[0])
                if os.name == 'nt' and name.startswith('/'):
                    name = name.lstrip('/')
            check_path(name, event)
    elif event in ('subprocess.Popen', 'os.system', 'os.startfile', 'os.posix_spawn'):
        deny(event, args[0])
    elif event.startswith('socket.') and event in (
            'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto'):
        address = args[1] if event != 'socket.getaddrinfo' else args[:2]
        allowed = (isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1')
                   and address[1] != 5179 and any(f.name in ('socketpair', '_fallback_socketpair')
                                                for f in traceback.extract_stack()))
        if not allowed:
            deny(event, address)
    elif event == 'import' and args[0].split('.')[0] in (
            'torch', 'whisper', 'whisperx', 'faster_whisper', 'transformers',
            'sentence_transformers', 'llama_cpp'):
        deny(event, args[0])

sys.addaudithook(audit)
selectors = sorted({str(p.relative_to(ROOT)).replace('\\', '/')
                    for pattern in GROUPS[group] for p in ROOT.glob(pattern)})
result = {'group': group, 'selectors': selectors, 'python': sys.version,
          'server_sha256': hashlib.sha256(server_copy.read_bytes()).hexdigest()}
try:
    if group in ('legacy', 'adapter', 'podcast', 'extra', 'phase4', 'heartbeat'):
        spec = importlib.util.spec_from_file_location('server', server_copy)
        server = importlib.util.module_from_spec(spec)
        sys.modules['server'] = server
        spec.loader.exec_module(server)
        server.HERE = ROOT
        server.DASHBOARD_PATH = ROOT / 'assets/dashboard/index.html'
        server.SPLASH_PATH = ROOT / 'assets/splash/index.html'
        server.DEFAULT_STYLE_ANCHORS_PATH = ROOT / 'defaults/style_anchors.json'
    import pytest
    result['exit_code'] = int(pytest.main([
        '-q', '-ra', '--tb=short', '--capture=sys', '-p', 'no:cacheprovider',
        '--basetemp=' + str(fixture / 't'), *selectors]))
finally:
    result['blocked_attempts'] = attempts
    (ROOT / '_scratch/as6' / (group + '-result.json')).write_text(
        json.dumps(result, indent=2), encoding='utf-8')
print('AS6_RESULT', json.dumps(result))
raise SystemExit(result['exit_code'])
