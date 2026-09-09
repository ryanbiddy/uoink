import ast,json,os,subprocess,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
HELPER=ROOT/'docs/library/proof/aw-rerun-2026-09-08/prepare_fixture.py'

def guard_code():
    tree=ast.parse(HELPER.read_text(encoding='utf-8'))
    return next(ast.literal_eval(n.value) for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='guard_code' for t in n.targets))

def test_safe_fixture_sqlite_file_uri_remains_allowed(tmp_path):
    import sqlite3
    db=tmp_path/'fixture evidence.db'
    c=sqlite3.connect(db);c.execute('create table evidence(x)');c.execute('insert into evidence values(7)');c.commit();c.close()
    script=tmp_path/'probe.py'
    script.write_text('import sqlite3\n'+guard_code()+"\nc=sqlite3.connect("+repr(db.as_uri()+'?mode=ro')+",uri=True)\nassert c.execute('select x from evidence').fetchone()[0]==7\nc.close()\n")
    env=os.environ.copy();env.update(AW_FIXTURE_ROOT=str(tmp_path),AW_FORBIDDEN_INDEX=os.environ['IG_FORBIDDEN_LIVE'])
    r=subprocess.run([sys.executable,'-B',str(script)],env=env,text=True,capture_output=True,timeout=10)
    assert r.returncode==0,r.stderr

@pytest.mark.parametrize('case',['outside','traversal','remote'])
def test_uri_guard_refuses_escape_without_opening_any_database(tmp_path,case):
    if case=='outside': value=(tmp_path.parent/'outside.db').as_uri()+'?mode=ro'
    elif case=='traversal': value=tmp_path.as_uri()+'/%2e%2e/outside.db?mode=ro'
    else: value='file://remote.invalid/share/index.db?mode=ro'
    script=tmp_path/'deny.py'
    script.write_text(guard_code()+"\ntry:\n audit('sqlite3.connect',("+repr(value)+",))\nexcept PermissionError:\n print('refused')\nelse:\n raise AssertionError('escape accepted')\n")
    env=os.environ.copy();env.update(AW_FIXTURE_ROOT=str(tmp_path),AW_FORBIDDEN_INDEX=os.environ['IG_FORBIDDEN_LIVE'])
    r=subprocess.run([sys.executable,'-B',str(script)],env=env,text=True,capture_output=True,timeout=10)
    assert r.returncode==0,r.stderr
    assert r.stdout.strip()=='refused'
