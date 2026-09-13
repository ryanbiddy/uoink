"""Root-admitted stdlib synthetic launcher; no real asset or model operations."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

OUT=Path(__file__).absolute().parent
FORBIDDEN=r'C:\Users\hello\AppData\Local\Uoink\index.db'
PYTHON=r'C:\Python314\python.exe'
CHILD_FILES=('plain_state_reader.py','qualify_reader.py','fixed-plan.json','INPUTS.json')
REQUIRED=CHILD_FILES+('launch.py','BRIEF.md','SOURCE-BINDINGS.json','EXPECTED-CASES.json',
    'context/fixed_converter.py.txt','context/fixed-factory.proposal.txt')
sha=lambda raw:hashlib.sha256(raw).hexdigest()

def save(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(json.dumps(value,indent=2)+'\n')

def verify_inputs(expected):
    if set(expected)!=set(REQUIRED):raise ValueError('Exact source/harness/context admission required')
    for name,digest in expected.items():
        if not re.fullmatch(r'[0-9a-f]{64}',digest):raise ValueError('Invalid admitted digest')
        if sha((OUT/name).read_bytes())!=digest:raise ValueError('Reviewed input bytes changed: '+name)

def main():
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise ValueError('Launch only with -I -S -B')
    parser=argparse.ArgumentParser()
    parser.add_argument('--admission',required=True)
    args=parser.parse_args()
    raw_admission=Path(args.admission).read_bytes()
    admission=json.loads(raw_admission.decode('utf-8-sig'))
    if admission.get('root_reviewed') is not True or not admission.get('review_document'):
        raise ValueError('Unexecuted proposal: exact root review/admission required')
    label=admission['label']
    if not isinstance(label,str) or not re.fullmatch(r'vpr[0-9]{2}',label):
        raise ValueError('Fresh vprNN label required')
    verify_inputs(admission['source_hashes'])
    if admission.get('scope')!='generated-synthetic-plain-state-only':raise ValueError('Wrong admission scope')
    run=OUT/'runs'/label
    run.mkdir(parents=True,exist_ok=False)
    (run/'root-admission.json').write_bytes(raw_admission)
    for name in CHILD_FILES:
        (run/name).write_bytes((OUT/name).read_bytes())
    environment={key:value for key,value in os.environ.items() if key.upper() in {'SYSTEMROOT','WINDIR'}}
    environment.update(IG_FORBIDDEN_LIVE=FORBIDDEN,PYTHONDONTWRITEBYTECODE='1',
        PYTHONUTF8='1',PYTHONIOENCODING='utf-8',HF_HUB_OFFLINE='1',
        TRANSFORMERS_OFFLINE='1',HF_DATASETS_OFFLINE='1',PYANNOTE_METRICS_ENABLED='0',
        TEMP=str(run),TMP=str(run),HOME=str(run),USERPROFILE=str(run),
        LOCALAPPDATA=str(run),APPDATA=str(run))
    command=[PYTHON,'-I','-S','-B',str(run/'qualify_reader.py')]
    save(run/'launch-plan.json',{'command':command,'cwd':str(run),
        'environment_variable_names':sorted(environment),
        'source_hashes':admission['source_hashes'],'started_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'Only generated synthetic bytes and exact reviewed text inputs; no model/native package import'})
    try:
        with (run/'stdout.json').open('xb') as stdout,(run/'stderr.log').open('xb') as stderr:
            child=subprocess.run(command,cwd=run,env=environment,stdout=stdout,stderr=stderr,timeout=60)
    except subprocess.TimeoutExpired:
        save(run/'actual-exit.json',{'actual_child_exit':None,'timed_out':True,'scope':'No passing result assigned'})
        raise
    save(run/'actual-exit.json',{'actual_child_exit':child.returncode,'timed_out':False})
    verify_inputs(admission['source_hashes'])
    for name in CHILD_FILES:
        if (run/name).read_bytes()!=(OUT/name).read_bytes():raise ValueError('Child input changed')
    report=json.loads((run/'stdout.json').read_text(encoding='utf-8'))
    expected_cases=json.loads((OUT/'EXPECTED-CASES.json').read_text(encoding='utf-8'))
    actual_cases=[row['case'] for row in report['cases']]
    if actual_cases!=expected_cases or len(actual_cases)!=len(set(actual_cases)):
        raise ValueError('Incomplete or different case membership')
    if report['qualification_exit']!=child.returncode:raise ValueError('Child/receipt exit mismatch')
    passed=sum(row['passed'] is True for row in report['cases'])
    if (passed!=report['passed'] or len(actual_cases)-passed!=report['failed']
        or report['case_count']!=len(actual_cases) or report['skipped']!=0):
        raise ValueError('Case totals mismatch')
    valid=report['guard']['valid'] and not report['guard']['unexpected_events']
    if not valid:raise ValueError('Invalid child guard; preserve raw outcome')
    if (run/'stderr.log').read_bytes():raise ValueError('Unexpected child stderr retained')
    save(run/'checked-result.json',{'case_count':len(actual_cases),'passed':report['passed'],
        'failed':report['failed'],'skipped':0,'actual_child_exit':child.returncode,
        'guard_valid':True,'inputs_unchanged':True,'complete_membership':True,
        'real_artifact_or_model_qualified':False})
    print(json.dumps({'label':label,'case_count':len(actual_cases),'passed':report['passed'],
        'failed':report['failed'],'actual_child_exit':child.returncode,'guard_valid':True}))
    return child.returncode

if __name__=='__main__':raise SystemExit(main())
