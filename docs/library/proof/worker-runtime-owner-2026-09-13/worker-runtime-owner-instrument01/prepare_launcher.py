"""Data-only adaptation of the retained launcher; no test/process invocation."""
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path('E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/worker-runtime-owner-instrument01')

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def write(name, text):
    with (HERE/name).open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(text)

def replace(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new, 1)

def main():
    mapping = json.loads((HERE/'SOURCE-INPUTS.json').read_text(encoding='utf-8'))['sources']
    expected = json.loads((HERE/'EXPECTED-CASES.json').read_text(encoding='utf-8'))
    original = (HERE/'before/run_namespace01.ps1').read_text(encoding='utf-8')
    current = original.replace('asr-worker-namespace-proposal01', 'worker-runtime-owner-instrument01')
    current = current.replace('nsp01', 'rto01').replace('qualify_namespace.py', 'qualify_owner.py').replace('run_namespace01.ps1', 'run_owner01.ps1')
    current = current.replace('namespace-fake-api-54-only', 'runtime-owner-generated-11-only')
    current = current.replace('uoink.namespace-expected-cases.v1', 'uoink.runtime-owner-expected-cases.v1')
    current = current.replace('uoink.worker-namespace-synthetic.v1', 'uoink.runtime-owner-synthetic.v1')
    current = current.replace('54 generated-memory fake API cases only', '11 generated fake factory and owner cases only')
    # Replace numeric case constants only; source pins are replaced separately.
    for before, after in (('-ne 54','-ne 11'),('-lt 54','-lt 11'),('-eq 54','-eq 11')):
        current = current.replace(before, after)
    start = current.index('$taskExpected=@{'); stop = current.index('\n$taskRecords=@()', start)
    expected_block = '$taskExpected=@{\n' + ''.join("    '"+name+"'='"+row['sha256']+"'\n" for name,row in mapping.items()) + '}\n'
    path_block = '$taskSourcePaths=@{\n' + ''.join("    '"+name+"'='"+row['path'].replace('/', '\\')+"'\n" for name,row in mapping.items()) + '}\n'
    names = tuple(mapping) + ('SOURCE-INPUTS.json', 'run_owner01.ps1')
    current = current[:start] + expected_block + path_block + '$taskInputNames=@(' + ','.join("'"+name+"'" for name in names) + ')' + current[stop:]
    current = replace(current, '    $taskSource=Join-Path $taskProposal $taskName',
        '    $taskSource=Join-Path $taskProposal $taskName\n'
        '    if($taskSourcePaths.ContainsKey($taskName)){$taskSource=$taskSourcePaths[$taskName]}')
    current = replace(current, '$taskAdmission=Get-Content -LiteralPath $taskAdmissionPath -Raw | ConvertFrom-Json',
        '$taskAdmissionHashBefore=(Get-FileHash -LiteralPath $taskAdmissionPath -Algorithm SHA256).Hash.ToLowerInvariant()\n'
        '$taskAdmission=Get-Content -LiteralPath $taskAdmissionPath -Raw | ConvertFrom-Json\n'
        "if((Get-FileHash -LiteralPath $taskAdmissionPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskAdmissionHashBefore){throw 'Admission changed during read'}")
    current = replace(current,
        "Copy-Item -LiteralPath $taskAdmissionPath -Destination (Join-Path $taskRun 'ROOT-ADMISSION.json') -ErrorAction Stop",
        "Copy-Item -LiteralPath $taskAdmissionPath -Destination (Join-Path $taskRun 'ROOT-ADMISSION.json') -ErrorAction Stop\n"
        "if((Get-FileHash -LiteralPath (Join-Path $taskRun 'ROOT-ADMISSION.json') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskAdmissionHashBefore){throw 'Admission copy mismatch'}")
    current = replace(current, "$taskAfter | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskRun 'after.json') -Encoding utf8",
        "$taskAdmissionSourceAfter=(Get-FileHash -LiteralPath $taskAdmissionPath -Algorithm SHA256).Hash.ToLowerInvariant()\n"
        "$taskAdmissionCopyAfter=(Get-FileHash -LiteralPath (Join-Path $taskRun 'ROOT-ADMISSION.json') -Algorithm SHA256).Hash.ToLowerInvariant()\n"
        "if($taskAdmissionSourceAfter -cne $taskAdmissionHashBefore -or $taskAdmissionCopyAfter -cne $taskAdmissionHashBefore){$taskUnchanged=$false}\n"
        "$taskAfter += [ordered]@{name='ROOT-ADMISSION.json';before_sha256=$taskAdmissionHashBefore;copy_after_sha256=$taskAdmissionCopyAfter;source_after_sha256=$taskAdmissionSourceAfter}\n"
        "$taskAfter | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskRun 'after.json') -Encoding utf8")
    current = replace(current, "        $taskResult.stdout_capture -ceq '' -and $taskResult.stderr_capture -ceq ''",
        "        $taskResult.methods_unchanged -ceq $true -and $taskResult.closed_entries_unchanged -ceq $true -and\n"
        "        $taskResult.owner_binding_valid -ceq $true -and\n"
        "        $taskResult.stdout_capture -ceq '' -and $taskResult.stderr_capture -ceq ''")
    write('run_owner01.ps1', current)
    write('run_owner01.ps1.diff', ''.join(difflib.unified_diff(original.splitlines(True), current.splitlines(True),
        fromfile='before/run_namespace01.ps1', tofile='run_owner01.ps1')))
    pins = {name: row['sha256'] for name, row in mapping.items()}
    pins['SOURCE-INPUTS.json'] = sha((HERE/'SOURCE-INPUTS.json').read_bytes())
    pins['run_owner01.ps1'] = sha((HERE/'run_owner01.ps1').read_bytes())
    admission = {'root_reviewed': False, 'scope': 'runtime-owner-generated-11-only', 'label': 'rto01',
                 'input_sha256': pins, 'expected_cases': expected['ordered_cases'],
                 'notice': 'Template only. No run is authorized until the root reviews these exact files.'}
    write('ROOT-ADMISSION.template.json', json.dumps(admission, indent=2) + '\n')
    # Exact receipt logic is retained; only the admitted child filename changes.
    def native_block(text):
        return text.split('# BEGIN EXACT NATIVE RECEIPT BLOCK',1)[1].split('# END EXACT NATIVE RECEIPT BLOCK',1)[0]
    assert native_block(original).replace('qualify_namespace.py','qualify_owner.py') == native_block(current)
    print(json.dumps({'launcher_sha256': pins['run_owner01.ps1'], 'admission_inputs':len(pins),
                      'expected_cases':11, 'native_block_logic_unchanged':True,'candidate_execution':False}))

if __name__ == '__main__':
    main()
