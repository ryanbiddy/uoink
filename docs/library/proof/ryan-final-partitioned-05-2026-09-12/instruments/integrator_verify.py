"""Integrator-only isolated verification. Does not modify implementation or tests."""
import argparse
import json
import os
from pathlib import Path
import site
import subprocess
import sys

p = argparse.ArgumentParser()
p.add_argument('--root', required=True)
p.add_argument('--label', required=True)
p.add_argument('--as9', action='store_true')
p.add_argument('selectors', nargs='*')
args, extras = p.parse_known_args()
root = Path(args.root).resolve()
scratch = root / '_scratch' / args.label
scratch.mkdir(parents=True, exist_ok=False)
packages = Path(site.getusersitepackages())
original_local = os.environ['LOCALAPPDATA']
guard = scratch / 'guard'
guard.mkdir()
(guard / 'ig_paths.py').write_text('import pytest\n@pytest.fixture\ndef tmp_path(tmp_path_factory):\n    return tmp_path_factory.mktemp("t")\n', encoding='utf-8')
(guard / 'sitecustomize.py').write_text('''import os, sys
def audit(event, args):
    if event in ('open', 'sqlite3.connect'):
        value = args[0]
        if isinstance(value, (str, bytes, os.PathLike)):
            name = os.fsdecode(value).replace('\\\\', '/').lower()
            forbidden = os.environ['IG_FORBIDDEN_LIVE'].replace('\\\\', '/').lower()
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
        if name.split('.')[0] in ('claude','codex','gemini','grok'):
            raise PermissionError('Integrator guard: real model process forbidden')
sys.addaudithook(audit)
''', encoding='utf-8')
env = os.environ.copy()
env.pop('ANTHROPIC_API_KEY', None)
env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1',
    PHASE3_REQUIRE_IMPLEMENTATION='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
    IG_FORBIDDEN_LIVE=str(Path(original_local) / 'Uoink' / 'index.db'),
    PYTHONPATH=os.pathsep.join(map(str, [guard, root, packages, packages/'win32', packages/'win32/lib', packages/'pythonwin'])))
for key in ('LOCALAPPDATA','APPDATA','XDG_DATA_HOME','TEMP','TMP','UOINK_DATA_ROOT','UOINK_OUTPUT_ROOT','UOINK_OUTPUT_DIR','YOINK_OUTPUT_DIR'):
    env[key] = str(scratch)
env['UOINK_INDEX_PATH'] = str(scratch / 'unused-index.db')
prefix = [sys.executable, '-B', '-m', 'pytest', '-q', '-ra', '--tb=short', '-p', 'no:cacheprovider', '-p', 'ig_paths']
groups = {}
if args.as9:
    groups['confirmation'] = prefix + ['tests/library_work_astra/test_phase3_acceptance8.py','tests/library_work_astra/test_phase3_acceptance9.py']
    groups['strict'] = prefix + [str(x.relative_to(root)) for x in sorted((root/'tests/library_work_astra').glob('test_phase3_*.py')) if x.name != 'test_phase3_s21.py']
    for group in ('service','dashboard','legacy','adapter','podcast','packaging','heartbeat','extra','phase4'):
        groups['companion-'+group] = [sys.executable, '-B', 'tests/library_work_astra/run_phase3_companions.py', group]
    groups['dashboard'] = prefix + ['tests/test_dashboard_sources_api.py','tests/test_dashboard_sources_ui.py','tests/test_dashboard_v324_ui.py']
else:
    groups['tests'] = prefix + args.selectors + extras
results = []
for i, (name, command) in enumerate(groups.items()):
    if '-m' in command:
        command += ['--basetemp='+str(root/'_scratch'/f'{args.label}-{i}'), '--junitxml='+str(scratch/(name+'.xml'))]
    log = scratch / (name+'.log')
    print('START', name, flush=True)
    with log.open('w', encoding='utf-8') as f:
        result = subprocess.run(command, cwd=root, env=env, stdout=f, stderr=subprocess.STDOUT)
    output = log.read_text(encoding='utf-8')
    print(name, 'exit', result.returncode, '\n'+'\n'.join(output.splitlines()[-18:]), flush=True)
    results.append({'name':name,'command':command,'exit':result.returncode,'log':str(log)})
    (scratch/'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
raise SystemExit(int(any(x['exit'] for x in results)))
