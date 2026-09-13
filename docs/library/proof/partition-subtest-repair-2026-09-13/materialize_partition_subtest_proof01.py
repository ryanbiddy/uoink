"""Copy frozen synthetic proof and explicit independent receipts only."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
WORKER = ROOT/'_scratch/partition-subtest-repair01'
OUT = ROOT/'docs/library/proof/partition-subtest-repair-2026-09-13'
assert not OUT.exists()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def verify_worker():
    assert digest(WORKER/'SHA256.json')=='9ee6e962038e64b83ee65dc5823190f39d61d3596fb0473e8dadce25b96b1b3b'
    files=read(WORKER/'SHA256.json')['files']
    assert len(files)==282
    assert {p.relative_to(WORKER).as_posix() for p in WORKER.rglob('*') if p.is_file()}==set(files)|{'SHA256.json'}
    for name,row in files.items():
        path=(WORKER/name).resolve(strict=True)
        assert path.is_relative_to(WORKER.resolve()) and path.stat().st_size==row['bytes'] and digest(path)==row['sha256']
    return files


files=verify_worker()
launch=ROOT/'_scratch/astra-partition-subtest01-launch'
raw=ROOT/'_scratch/astra-partition-subtest01'
validated=read(launch/'validated.json')
assert validated['result']=='PASS' and validated['counts']=={'passed':116} and validated['subtest_count']==0
assert validated['pytest_exit']==validated['outer_exit']==0
assert read(launch/'actual-exit.json')['outer_verifier_exit']==0 and read(raw/'results.json')[0]['exit']==0
assert read(launch/'plan.json')['input_sha256']==read(launch/'after.json')
assert '116 passed in 0.37s' in (raw/'tests.log').read_text()
guard=read(launch/'heavy-guard.json')
assert guard['already_loaded_at_startup']==[] and guard['blocked_import_attempts']==[]
assert guard['guard_installed_at_finish'] is True and guard['pytest_exitstatus']==0
planned=[(WORKER/name,'worker/'+name) for name in files]
planned.append((WORKER/'SHA256.json','worker/ORIGINAL-WORKER-SHA256.json'))
launch_files=('actual-exit.json','after.json','validated.json','stdout.log','stderr.log','heavy-guard.json','guard-validation.json','plan.json','partition/session.json','partition/reports.jsonl','partition/membership.json','probe/session.json','probe/reports.jsonl','probe/membership.json','probe/hooks.json')
assert {p.relative_to(launch).as_posix() for p in launch.rglob('*') if p.is_file()}==set(launch_files)
planned += [(launch/name,'independent/launch/'+name) for name in launch_files]
raw_files=('tests.xml','tests.log','results.json','guard/sitecustomize.py','guard/ig_paths.py')
assert {p.relative_to(raw).as_posix() for p in raw.rglob('*') if p.is_file()}==set(raw_files)
planned += [(raw/name,'independent/raw/'+name) for name in raw_files]
planned += [(ROOT/'_scratch/verify_partition_subtest_astra01.py','independent/verify_partition_subtest_astra01.py'),
            (ROOT/'_scratch/PARTITION-SUBTEST-FINAL-VERDICT-2026-09-13.md','REVIEW.md'),
            (ROOT/'_scratch/partition-subtest-repair01-seal.log','worker-seal.log'),
            (Path(__file__),'materialize_partition_subtest_proof01.py')]
OUT.mkdir()
copies=[]
for source,relative in planned:
    assert source.is_file() and not source.is_symlink()
    target=OUT/relative
    assert target.resolve().is_relative_to(OUT.resolve()) and not target.exists()
    before=digest(source)
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)
    assert digest(source)==digest(target)==before
    copies.append({'source':str(source),'destination':relative,'bytes':source.stat().st_size,'sha256':before})
verify_worker()
(OUT/'.gitattributes').write_bytes(b'* -text\n')
(OUT/'COPY-VERIFICATION.json').write_text(json.dumps({'verified_utc':datetime.now(timezone.utc).isoformat(),'copies':copies,'original_worker_payloads_verified':282,'original_worker_seal_unchanged':True,'independent_cases':116,'independent_subtests':0,'independent_log_seconds':0.37,'hash_mismatches':0},indent=2)+'\n',encoding='utf-8')
payloads={p.relative_to(OUT).as_posix():{'bytes':p.stat().st_size,'sha256':digest(p)} for p in sorted(OUT.rglob('*')) if p.is_file()}
(OUT/'SHA256.json').write_text(json.dumps({'algorithm':'sha256','files':payloads},indent=2)+'\n',encoding='utf-8')
for name,row in payloads.items():
    assert digest(OUT/name)==row['sha256']
print(json.dumps({'copied_files':len(copies),'payload_count':len(payloads),'hash_mismatches':0,'manifest_sha256':digest(OUT/'SHA256.json'),'worker_seal_unchanged':True,'independent_passes':116,'independent_seconds':0.37},indent=2))
