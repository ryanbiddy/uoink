"""Read-only installed diagnostic; not an acceptance/client rerun."""
from pathlib import Path
import datetime as dt, hashlib, json, os, stat, subprocess, sys, traceback

repo = Path(__file__).resolve().parents[1]
root = Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 06')
profile = root / 'p4-native01/profile'
app = root / 'app'
seal = repo / 'docs/library/proof/candidate-package-06-2026-09-11'
out = root / 'p4-native01/media-storage-diagnostic03'
for key in list(os.environ):
    if key.endswith(('API_KEY', '_TOKEN', '_SECRET')) or key.startswith('CLAUDE_CODE_USE_') or key in ('ANTHROPIC_BASE_URL', 'PYTHONPATH'):
        os.environ.pop(key, None)
os.environ.update(IG_FORBIDDEN_LIVE=r'C:\Users\hello\AppData\Local\Uoink\index.db',
                  HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', PYTHONDONTWRITEBYTECODE='1')
sys.path.insert(0, str(repo / 'scripts/install_receipt'))
import p4_common as common
from p4_session import spawn_owned

def sha(path):
    with path.open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()

def save(path, value):
    with path.open('x', encoding='utf8') as f: f.write(json.dumps(value, indent=2, default=str) + '\n')

for entry in (profile, *profile.parents):
    assert not entry.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
kwargs = dict(isolated_profile=profile, isolated_port=18282, receipt_root=profile.parent,
              installed_app=app, installed_interpreter=app/'python/python.exe',
              package_manifest=seal/'package-manifest.json', forbid_checkout=repo,
              package_path=repo/'build/Uoink-Setup-3.8.0.exe', source_bindings_path=seal/'source-bindings.json')

if '--child' in sys.argv:
    binding = common.validate_isolation(**kwargs, runtime_mode='installed')
    sys.path.insert(0, str(app))
    import uoink_install_isolation as isolation
    isolation.apply_from_process()
    import index, library_media as media, library_resources as resources, uoink_mcp, uoink_mcp_tools, server
    assert Path(media.__file__).resolve() == app/'library_media.py'
    database = Path(binding['index_path'])
    assert database.resolve() == profile/'index.db'
    result = {'diagnostic_only': True, 'installed_credit': False, 'sql': [], 'module': str(media.__file__)}
    assert Path(server.INDEX_PATH).resolve() == database.resolve()
    idx = server._get_existing_index()
    result['exceptions'] = []
    def trace(frame,event,arg):
        if event == 'exception' and Path(frame.f_code.co_filename).resolve() in (app/'library_media.py', app/'library_resources.py'):
            kind,exc,tb = arg
            result['exceptions'].append({'function':frame.f_code.co_name,'line':frame.f_lineno,'type':kind.__name__,'message':str(exc),'sqlite_errorcode':getattr(exc,'sqlite_errorcode',None)})
        return trace
    try:
        idx._conn.set_trace_callback(result['sql'].append)
        sys.settrace(trace)
        result['inventory'] = resources.make_reader(server).list_resources()
        import time
        time.sleep(2.1)
        result['result'] = uoink_mcp_tools.call_tool('export_cited_range', {'video_id':'p4fx-timed-01','start':34,'end':46})
    except Exception as exc:
        result.update(error=type(exc).__name__+': '+str(exc), traceback=traceback.format_exc(),
                      sqlite_errorcode=getattr(exc, 'sqlite_errorcode', None),
                      sqlite_errorname=getattr(exc, 'sqlite_errorname', None))
    finally:
        sys.settrace(None)
        idx.close()
    save(out/'diagnostic.json', result)
    print(json.dumps(result, indent=2))
    raise SystemExit(0)

assert sys.flags.isolated and sys.flags.no_site
out.mkdir(exist_ok=False)
binding = common.validate_isolation(**kwargs, runtime_mode='source-runtime', probe_runtime=False)
binding['runtime_mode'] = 'installed'
env = common.isolation_env(binding)
prep = json.loads((profile/'client/client-config-preparation.json').read_text())
def prepared():
    return all(sha(profile/'client'/name)==digest for name,digest in prep['hashes'].items())
assert prepared()
database = profile/'index.db'
db_before = sha(database)
pth = app/'python/python313._pth'
pth_before = sha(pth)
assert not (app/'python/Lib/site-packages/sitecustomize.py').exists()
guard_record = None
safe = True
record = {'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(), 'diagnostic_only':True,
          'prepared_before':True, 'database_before':db_before, 'instrument_sha256':sha(Path(__file__))}
try:
    guard = common.write_guard(profile,binding)
    guard_record = common.install_guard_into_interpreter(app/'python/python.exe',guard,installed_app=app)
    record['guard_canary'] = common.prove_guard_canary(interpreter=app/'python/python.exe',env=env,profile=profile,cwd=profile)
    assert record['guard_canary']['refused']
    command = [str(app/'python/python.exe'),'-P','-B','-s',str(Path(__file__)), '--child']
    record['command'] = command
    with (out/'stdout').open('xb') as stdout, (out/'stderr').open('xb') as stderr:
        child = spawn_owned(command, cwd=profile,env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,label='media-storage-diagnostic01')
        safe = False
        try:
            record['exit'] = child.wait(timeout=45)
        finally:
            record['cleanup'] = child.terminate_tree(timeout=5)
            safe = bool(record['cleanup'].get('cleaned'))
finally:
    if safe: record['guard_restore'] = common.restore_guard(guard_record)
    record.update(prepared_after=prepared(), database_after=sha(database) if safe else None,
                  pth_unchanged=sha(pth)==pth_before,
                  guard_absent=not (app/'python/Lib/site-packages/sitecustomize.py').exists())
    save(out/'outer.json', record)
print(json.dumps({k:v for k,v in record.items() if k in ('exit','prepared_after','database_before','database_after','pth_unchanged','guard_absent')},indent=2))
assert safe and record['exit']==0 and record['database_before']==record['database_after'] and record['prepared_after'] and record['pth_unchanged'] and record['guard_absent']
