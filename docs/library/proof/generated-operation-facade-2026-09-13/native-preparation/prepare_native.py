"""Data-only fixed text preparation; no candidate/native imports or invocation."""
from pathlib import Path
import ast
import difflib
import hashlib
import json

BASE = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
HERE = Path(__file__).parent
OLD = BASE / "_scratch/child-readset-adoption-proposal02"
FLOW = BASE / "_scratch/generated-operation-facade-proposal01/generated_operation_flow.py"

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def put(name, value):
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(value.encode() if isinstance(value,str) else value)

def delta(name, old, new):
    put(name, ''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='before/'+name,tofile='after/'+name)))

original_map = (OLD / "SOURCE-INPUTS.json").read_bytes()
mapping = json.loads(original_map)
for name, source in mapping["source_paths"].items():
    assert sha(Path(source).read_bytes()) == mapping["source_sha256"][name]
put('original/SOURCE-INPUTS.json', original_map)
old_boot_raw = (OLD / 'dummy_bootstrap.py').read_bytes()
old_launch_raw = (OLD / 'run_adoption01.ps1').read_bytes()
old_flow_raw = FLOW.read_bytes()
assert sha(old_boot_raw) == '83850d5426ae75a3b16ed5503a536a2202f541cb002929fa0dd52ef0c9cdfa06'
assert sha(old_launch_raw) == '0bb77f068bdc1273abd0423ffb76904f919a0d6edb7f136871b35cee812bf10f'
assert sha(old_flow_raw) == '42b93c5455577d6efefd4406b83fb5d5e54eb943ea790d46e4075706dad33a8e'
put('original/dummy_bootstrap.py',old_boot_raw)
put('original/run_adoption01.ps1',old_launch_raw)
put('original/generated_operation_flow.py',old_flow_raw)
boot = old_boot_raw.decode().replace('\r\n','\n')
launch = old_launch_raw.decode().replace('\r\n','\n')
flow = old_flow_raw.decode().replace('\r\n','\n')
old_boot, old_launch, old_flow = boot, launch, flow
run_paths = {mode:str(BASE / ('_scratch/generated-operation-'+mode+'01')) for mode in ('drain','cancel')}

# Receipt-only additions. Preserve every existing assertion and operation body.
flow = flow.replace('self.operation_events = []', 'self.operation_events = []\n        self.start_observation = None',1)
flow = flow.replace('            self._cursor = object()', '            self.start_observation = dict(payload)\n            self._cursor = object()',1)
flow = flow.replace('"operation_events": port.operation_events, "cursor_state": port._cursor_state,',
    '"operation_events": port.operation_events, "cursor_state": port._cursor_state,\n            "cursor_start": port.start_observation,')
flow = flow.replace('state, index, actions = "new", 0, []', 'state, index, actions = "new", 0, []\n    start_observation = None')
flow = flow.replace('"produced_segments": index, "generated_duration_only": True}',
    '"produced_segments": index, "generated_duration_only": True, "cursor_start": start_observation}')
flow = flow.replace('response_operation, response = "done", {"cursor_id": CURSOR_ID, "started": True, "produced_segments": 0}',
    'response_operation, response = "done", {"cursor_id": CURSOR_ID, "started": True, "produced_segments": 0}\n            start_observation = dict(response)')
assert [ast.dump(n) for n in ast.walk(ast.parse(flow)) if isinstance(n,ast.Assert)] == [ast.dump(n) for n in ast.walk(ast.parse(old_flow)) if isinstance(n,ast.Assert)]
put('generated_operation_flow.py',flow)
delta('operation-receipt.diff',old_flow,flow)

begin = boot.index('FIXED_RUNS = {')
end = boot.index('assert sys.flags.isolated',begin)
boot = boot[:begin] + 'FIXED_RUNS = ' + repr(run_paths) + '''
LOCATION = os.path.normcase(os.path.dirname(os.path.abspath(__file__)))
MODE = next((mode for mode, path in FIXED_RUNS.items() if os.path.normcase(path) == LOCATION), None)
assert MODE is not None, "fixed_fresh_generated_operation_directory"
CASE = "positive"
EXPECTED_RUN = FIXED_RUNS[MODE]
''' + boot[end:]
boot = boot.replace('"pinned_buffer_namespace", "inherited_readset", "generated_worker_flow")',
                    '"pinned_buffer_namespace", "inherited_readset", "generated_worker_flow", "generated_operation_flow")',1)
boot = boot.replace('admission["scope"] == "five-generated-inherited-files-only"', 'admission["scope"] == "generated-operation-facade-only"')
boot = boot.replace('assert admission["case"] == CASE and admission["run_path"] == EXPECTED_RUN',
    'assert admission["case"] == CASE and admission["operation_mode"] == MODE and admission["run_path"] == EXPECTED_RUN')
boot = boot.replace('"pinned_buffer_namespace", "inherited_readset", "generated_worker_flow"))',
                    '"pinned_buffer_namespace", "inherited_readset", "generated_operation_flow"))',1)
boot = boot.replace('os.urandom(32), os.urandom(32), CASE)', 'os.urandom(32), os.urandom(32), CASE, operation_mode=MODE)')
boot = boot.replace('"schema": "uoink.generated-inherited-readset.v1", "role": ROLE, "case": CASE,',
                    '"schema": "uoink.generated-operation-facade.v1", "role": ROLE, "case": CASE, "operation_mode": MODE,')
ast.parse(boot)
# Whole fixed dispatcher, monitor, import/audit functions and finalizer unchanged.
old_ast = ast.parse(old_boot)
new_ast = ast.parse(boot)
for name in ('audit','early_audit','FixedNativeDispatch','NativeMonitor','FixedFinder','VerifiedCtypesLoader'):
    old_node = next(n for n in old_ast.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name==name)
    new_node = next(n for n in new_ast.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name==name)
    assert ast.dump(old_node)==ast.dump(new_node),name
assert ast.dump(old_ast.body[-1].finalbody[0]) == ast.dump(new_ast.body[-1].finalbody[0])
put('dummy_bootstrap.py',boot)
delta('bootstrap-from-adoption.diff',old_boot,boot)

mapping['source_paths']['generated_operation_flow.py'] = str(HERE / 'generated_operation_flow.py')
mapping['source_sha256']['generated_operation_flow.py'] = sha(flow.encode())
mapping['source_paths']['dummy_bootstrap.py'] = str(HERE / 'dummy_bootstrap.py')
mapping['source_sha256']['dummy_bootstrap.py'] = sha(boot.encode())
map_text=json.dumps(mapping,indent=2)+'\n'
put('SOURCE-INPUTS.json',map_text)
delta('source-map.diff',original_map.decode(),map_text)

launch = launch.replace("param([Parameter(Mandatory=$true)][ValidateSet('positive','wrong_identity')][string]$taskCase)",
    "param([Parameter(Mandatory=$true)][ValidateSet('drain','cancel')][string]$taskMode)\n$taskCase='positive'")
launch = launch.replace(str(OLD),str(HERE)).replace("run_adoption01.ps1","run_operation01.ps1")
start=launch.index('$taskRuns=@{')
end=launch.index("$taskPython=",start)
launch=launch[:start]+"$taskRuns=@{"+';'.join(mode+"='"+path+"'" for mode,path in run_paths.items())+"}\n$taskRun=$taskRuns[$taskMode]\n"+launch[end:]
launch=launch.replace("('ROOT-ADMISSION-'+$taskCase+'.json')","('ROOT-ADMISSION-'+$taskMode+'.json')")
launch=launch.replace("'five-generated-inherited-files-only'", "'generated-operation-facade-only'")
launch=launch.replace("$taskAdmission.case -cne $taskCase -or", "$taskAdmission.case -cne $taskCase -or $taskAdmission.operation_mode -cne $taskMode -or")
start=launch.index('$taskSharedNames=@(')
end=launch.index('$taskNativePaths=@(',start)
source_block='$taskPaths=[ordered]@{\n'+''.join("    '"+name+"'='"+path+"'\n" for name,path in mapping['source_paths'].items())+'}\n'
source_block+='''if(@($taskMap.source_paths.PSObject.Properties).Count -ne 9 -or @($taskMap.source_sha256.PSObject.Properties).Count -ne 9 -or @($taskMap.native_bindings.PSObject.Properties).Count -ne 9){throw 'Fixed input membership refused'}
foreach($taskName in $taskPaths.Keys){
    $taskPath=$taskPaths[$taskName]
    $taskHash=(Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if($taskMap.source_paths.$taskName -cne $taskPath -or $taskMap.source_sha256.$taskName -cne $taskHash){throw 'Fixed source input differs'}
    $taskSources += [ordered]@{name=$taskName;path=$taskPath;sha256=$taskHash}
}
'''
launch=launch[:start]+source_block+launch[end:]
launch=launch.replace("scope='Five newly generated ASCII files; no model data';case=$taskCase;", "scope='Generated facade with five newly generated ASCII files; no model data';case=$taskCase;operation_mode=$taskMode;")
launch=launch.replace("$taskReceipt.schema -cne 'uoink.generated-inherited-readset.v1'", "$taskReceipt.schema -cne 'uoink.generated-operation-facade.v1' -or $taskReceipt.operation_mode -cne $taskMode")
launch=launch.replace("scope='Generated inherited file data path only; no model acceptance'", "operation_mode=$taskMode;scope='Generated OperationFacade only; no model acceptance'")
extra='''
    # Exact generated operation observations, in addition to unchanged native/adoption checks.
    $taskExpectedCount=2
    $taskExpectedState='eof'
    $taskExpectedActions=@('admit_generated_media','begin_generated_transcription','next_generated_segment','next_generated_segment','next_generated_segment')
    if($taskMode -ceq 'cancel'){
        $taskExpectedCount=1
        $taskExpectedState='cancelled'
        $taskExpectedActions=@('admit_generated_media','begin_generated_transcription','next_generated_segment','cancel_generated_cursor')
    }
    if($taskResult.operation_mode -cne $taskMode -or $taskResult.cursor_state -cne $taskExpectedState -or $taskChild.result.cursor_state -cne $taskExpectedState -or $taskChild.result.produced_segments -ne $taskExpectedCount -or $taskResult.retained_facade_and_stream_refused -cne $true -or $taskChild.result.generated_duration_only -cne $true){$taskValid=$false}
    foreach($taskObserved in @($taskResult,$taskChild.result)){
        if(@($taskObserved.operation_events).Count -ne $taskExpectedActions.Count){$taskValid=$false}
        for($taskIndex=0;$taskIndex -lt $taskExpectedActions.Count;$taskIndex++){
            if($taskObserved.operation_events[$taskIndex] -cne $taskExpectedActions[$taskIndex]){$taskValid=$false}
        }
        if(@($taskObserved.cursor_start.PSObject.Properties).Count -ne 3 -or $taskObserved.cursor_start.cursor_id -cne 'generated-cursor-01' -or $taskObserved.cursor_start.started -isnot [bool] -or $taskObserved.cursor_start.started -cne $true -or $taskObserved.cursor_start.produced_segments -isnot [long] -and $taskObserved.cursor_start.produced_segments -isnot [int] -or $taskObserved.cursor_start.produced_segments -ne 0){$taskValid=$false}
    }
    $taskTextNames=@('config.json','tokenizer.json')
    if(@($taskResult.segments).Count -ne $taskExpectedCount){$taskValid=$false}
    for($taskIndex=0;$taskIndex -lt $taskExpectedCount;$taskIndex++){
        $taskSegment=$taskResult.segments[$taskIndex]
        $taskExpectedText='Uoink generated adoption fixture: '+$taskTextNames[$taskIndex]+'. No model data.'
        if(@($taskSegment.PSObject.Properties).Count -ne 4 -or $taskSegment.start -isnot [double] -or $taskSegment.end -isnot [double] -or $taskSegment.start -ne ($taskIndex/2.0) -or $taskSegment.end -ne (($taskIndex+1)/2.0) -or $taskSegment.text -isnot [string] -or $taskSegment.text -cne $taskExpectedText -or @($taskSegment.words).Count -ne 0){$taskValid=$false}
    }
    if($taskChild.result.readback.payload_bytes -ne 328 -or $taskChild.result.readback.namespace_sha256 -cne $taskManifest.namespace_sha256){$taskValid=$false}
'''
launch=launch.replace("}catch{$taskValid=$false;$taskReceiptError=$_.Exception.GetType().Name}",extra+"}catch{$taskValid=$false;$taskReceiptError=$_.Exception.GetType().Name}")
start_marker='# BEGIN EXACT NATIVE RECEIPT BLOCK'
end_marker='# END EXACT NATIVE RECEIPT BLOCK'
assert old_launch.split(start_marker)[1].split(end_marker)[0]==launch.split(start_marker)[1].split(end_marker)[0]
put('run_operation01.ps1',launch)
delta('launcher-from-adoption.diff',old_launch,launch)
for mode,path in run_paths.items():
    admission={'root_reviewed':False,'scope':'generated-operation-facade-only','case':'positive','operation_mode':mode,
               'run_path':path,'source_inputs_sha256':sha(map_text.encode()),'launcher_sha256':sha(launch.encode()),
               'real_runtime_approval':False,'model_calls_authorized':False,'new_native_apis':[]}
    put('ROOT-ADMISSION-'+mode+'.template.json',json.dumps(admission,indent=2)+'\n')
bindings={'candidate_executions':0,'new_native_apis':[],'fixed_dispatch_functions':32,'fixed_support_inputs':9,
          'fixed_source_inputs':9,'guard_dispatch_monitor_finalizer_ast_unchanged':True,'native_exit_marked_block_unchanged':True,
          'source_assertions_unchanged':True,'bootstrap_sha256':sha(boot.encode()),'operation_sha256':sha(flow.encode()),
          'launcher_sha256':sha(launch.encode()),'source_map_sha256':sha(map_text.encode()),'run_paths':run_paths}
put('PREPARATION-BINDINGS.json',json.dumps(bindings,indent=2)+'\n')
print(json.dumps(bindings,indent=2))
