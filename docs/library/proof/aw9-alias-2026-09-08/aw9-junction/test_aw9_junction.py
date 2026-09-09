"""Read-only gate probe through an owned junction alias."""
import json,subprocess,sys,os
from pathlib import Path
import library_mirror as m
from tests.library_work_astra.test_phase4_aw_acceptance import env

def test_same_destination_junction_alias_uses_same_gate(env):
    original=str(env.vault);alias=str(env.vault.parent/'v-alias')
    child_env=os.environ.copy();child_env.update(AW_ALIAS_LINK=alias,AW_ALIAS_TARGET=original)
    made=subprocess.run(['pwsh','-NoProfile','-Command','New-Item -ItemType Junction -Path $env:AW_ALIAS_LINK -Target $env:AW_ALIAS_TARGET | Out-Null'],env=child_env,capture_output=True,text=True,timeout=8)
    assert made.returncode==0,made.stderr
    assert Path(original).samefile(alias)
    h,k=m._win_acquire_dest_mutex(original,0.25)
    try:
        source="""import json,sys
import library_mirror as m
try:
 h,k=m._win_acquire_dest_mutex(sys.argv[1],0.25)
except m._LockTimeout:
 print(json.dumps({'acquired':False}))
else:
 print(json.dumps({'acquired':True,'key':k}))
 m._win_release_dest_mutex(h,k)
"""
        p=subprocess.run([sys.executable,'-B','-c',source,alias],capture_output=True,text=True,timeout=8)
        assert p.returncode==0,p.stderr
        result=json.loads(p.stdout);result.update(original=original,alias=alias,same_file=True)
        assert not result['acquired'],result
    finally:m._win_release_dest_mutex(h,k)
