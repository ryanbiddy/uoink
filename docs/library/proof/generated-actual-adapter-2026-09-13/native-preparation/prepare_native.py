"""Data-only bootstrap/launcher derivation; no source or native execution."""
from pathlib import Path
import ast
import difflib
import hashlib
import json
BASE=Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
HERE=Path(__file__).parent
OLD=BASE/'_scratch/generated-operation-native-proposal01'
BRIDGE=BASE/'_scratch/generated-actual-adapter-proposal01/generated_adapter_flow.py'
RUN=str(BASE/'_scratch/generated-actual-adapter-drain01')

def sha(raw):return hashlib.sha256(raw).hexdigest()
def put(name,data):
    path=HERE/name
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(data.encode() if isinstance(data,str) else data)
def diff(name,before,after):
    put(name,''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='original/'+name,tofile='current/'+name)))

map_raw=(OLD/'SOURCE-INPUTS.json').read_bytes()
mapping=json.loads(map_raw)
for name,path in mapping['source_paths'].items():assert sha(Path(path).read_bytes())==mapping['source_sha256'][name]
boot_raw=(OLD/'dummy_bootstrap.py').read_bytes()
launch_raw=(OLD/'run_operation01.ps1').read_bytes()
bridge_raw=BRIDGE.read_bytes()
assert sha(boot_raw)=='ff892a9b7e6f7b099be5baa7e86994cd72fa330edcf5078c296f6a1a5feea375'
assert sha(launch_raw)=='93408fac033823ef1db833d7886668e571aef4db968a9e9f76375a818b14dc07'
assert sha(bridge_raw)=='0cb972480f9aadb11d3ffffc2e7646b54d6dc01698a281a18cdad9759f177ae0'
for name,data in [('dummy_bootstrap.py',boot_raw),('run_operation01.ps1',launch_raw),('SOURCE-INPUTS.json',map_raw)]:put('original/'+name,data)
boot=boot_raw.decode().replace('\r\n','\n'); old_boot=boot
launch=launch_raw.decode().replace('\r\n','\n'); old_launch=launch
start=boot.index('FIXED_RUNS = ');end=boot.index('\nLOCATION = ',start)
boot=boot[:start]+'FIXED_RUNS = '+repr({'drain':RUN})+boot[end:]
boot=boot.replace('"generated_worker_flow", "generated_operation_flow")',
    '"generated_worker_flow", "generated_operation_flow",\n           "trusted_asr_resolver", "asr_loading_adapter", "generated_adapter_flow")',1)
boot=boot.replace('"generated-operation-facade-only"','"generated-actual-asr-adapter-only"')
boot=boot.replace('"pinned_buffer_namespace", "inherited_readset", "generated_operation_flow"))',
    '"pinned_buffer_namespace", "inherited_readset", "generated_adapter_flow"))',1)
boot=boot.replace('assert ADOPTION.NAMES == GENERATED_NAMES', '''REAL_RESOLVER = sys.modules["trusted_asr_resolver"]
ADAPTER = sys.modules["asr_loading_adapter"]
ORIGINAL_REAL_FUNCTIONS = (REAL_RESOLVER.load_manifest, REAL_RESOLVER.admit_snapshot, REAL_RESOLVER.bind_for_constructor)
ORIGINAL_ADAPTER_RELEASE = ADAPTER._release
ADAPTER_GLOBAL_NAMES = ("RELEASE_AUTHORITY", "RUNTIME_PROFILE", "SNAPSHOT_LIFECYCLE", "RUNTIME_FACTORY", "ACQUISITION_SERVICE")
assert REAL_RESOLVER.REAL_APPROVAL is None and ADAPTER.resolver is REAL_RESOLVER
assert all(getattr(ADAPTER, name) is None for name in ADAPTER_GLOBAL_NAMES)
assert ADOPTION.NAMES == GENERATED_NAMES''',1)
boot=boot.replace('    guard = (dispatch.valid', '''    adapter_state = {
        "real_approval_none": REAL_RESOLVER.REAL_APPROVAL is None,
        "real_functions_unchanged": (REAL_RESOLVER.load_manifest, REAL_RESOLVER.admit_snapshot, REAL_RESOLVER.bind_for_constructor) == ORIGINAL_REAL_FUNCTIONS,
        "private_release_restored": ADAPTER._release is ORIGINAL_ADAPTER_RELEASE,
        "services_unconfigured": all(getattr(ADAPTER, name) is None for name in ADAPTER_GLOBAL_NAMES),
        "resolver_module_restored": ADAPTER.resolver is REAL_RESOLVER,
    }
    guard = (all(adapter_state.values()) and dispatch.valid''',1)
boot=boot.replace('"schema": "uoink.generated-operation-facade.v1"','"schema": "uoink.generated-actual-asr-adapter.v1"')
boot=boot.replace('"native_exit_planned": code,', '"adapter_state": adapter_state, "native_exit_planned": code,',1)
old_tree=ast.parse(old_boot);new_tree=ast.parse(boot)
for name in ('audit','early_audit','FixedNativeDispatch','NativeMonitor','FixedFinder','VerifiedCtypesLoader'):
    get=lambda tree:next(n for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name==name)
    assert ast.dump(get(old_tree))==ast.dump(get(new_tree)),name
assert ast.dump(old_tree.body[-1].finalbody[0])==ast.dump(new_tree.body[-1].finalbody[0])
put('dummy_bootstrap.py',boot);diff('bootstrap.diff',old_boot,boot)
extra={
 'trusted_asr_resolver.py':(BASE/'_scratch/asr-trusted-manifest-resolver-proof02/proposal/trusted_asr_resolver.py','16a5a1245f649a3eb04d077b661835503f08bef0ff8822dcb545176f0cc30833'),
 'asr_loading_adapter.py':(BASE/'_scratch/asr-permit-facade-proposal01/asr_loading_adapter.py','2b6cbbad24264423e520bac54b7c2fb4c40ae771e5c15b08381dac1d2228a63c'),
 'generated_adapter_flow.py':(BRIDGE,sha(bridge_raw)),
}
for name,(path,digest) in extra.items():
    assert sha(path.read_bytes())==digest
    mapping['source_paths'][name]=str(path);mapping['source_sha256'][name]=digest
mapping['source_paths']['dummy_bootstrap.py']=str(HERE/'dummy_bootstrap.py')
mapping['source_sha256']['dummy_bootstrap.py']=sha(boot.encode())
map_text=json.dumps(mapping,indent=2)+'\n'
put('SOURCE-INPUTS.json',map_text);diff('source-map.diff',map_raw.decode(),map_text)

# Derive fixed expected policy data from source literals, not imported modules.
resolver_tree=ast.parse(extra['trusted_asr_resolver.py'][0].read_bytes())
specs=next(n.value for n in resolver_tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MODEL_SPECS' for t in n.targets))
row=next(v for k,v in zip(specs.keys,specs.values) if ast.literal_eval(k)=='large-v3-turbo')
revision=ast.literal_eval(row.elts[1])
names=('config.json','model.bin','preprocessor_config.json','tokenizer.json','vocabulary.json')
generated={name:('Uoink generated adoption fixture: '+name+'. No model data.\n').encode('ascii') for name in names}
recipe={'purpose':'generated-adapter-connection-only','profile_id':'generated-asr-reliability-v1','choice':'large-v3-turbo','revision':revision,
        'files':[{'name':name,'bytes':len(generated[name]),'sha256':sha(generated[name])} for name in names]}
recipe_sha=sha(json.dumps(recipe,sort_keys=True,separators=(',',':')).encode('ascii'))
namespace_sha=sha(json.dumps([[name,len(generated[name]),sha(generated[name])] for name in names],separators=(',',':')).encode('ascii'))
put('EXPECTED-GENERATED-POLICY.json',json.dumps({'recipe':recipe,'recipe_sha256':recipe_sha,'namespace_sha256':namespace_sha},indent=2)+'\n')

launch=launch.replace("[ValidateSet('drain','cancel')]","[ValidateSet('drain')]")
launch=launch.replace(str(OLD),str(HERE)).replace('run_operation01.ps1','run_actual_adapter01.ps1')
start=launch.index('$taskRuns=@{');end=launch.index('\n$taskRun=',start)
launch=launch[:start]+"$taskRuns=@{drain='"+RUN+"'}"+launch[end:]
launch=launch.replace("'generated-operation-facade-only'","'generated-actual-asr-adapter-only'")
start=launch.index('$taskPaths=[ordered]@{');end=launch.index('\nif(@($taskMap.source_paths',start)
launch=launch[:start]+'$taskPaths=[ordered]@{\n'+''.join("    '"+name+"'='"+path+"'\n" for name,path in mapping['source_paths'].items())+'}'+launch[end:]
launch=launch.replace('source_paths.PSObject.Properties).Count -ne 9','source_paths.PSObject.Properties).Count -ne 12').replace('source_sha256.PSObject.Properties).Count -ne 9','source_sha256.PSObject.Properties).Count -ne 12')
launch=launch.replace("'uoink.generated-operation-facade.v1'","'uoink.generated-actual-asr-adapter.v1'")
launch=launch.replace("scope='Generated facade with five newly generated ASCII files; no model data'","scope='Actual adapter and generated facade with five ASCII files; no model data'")
launch=launch.replace("scope='Generated OperationFacade only; no model acceptance'","scope='Actual ASR adapter with generated data only; no model acceptance'")
checks='''
    # Actual-adapter state is observed independently by the unchanged-guard bootstrap.
    $taskStateNames=@('real_approval_none','real_functions_unchanged','private_release_restored','services_unconfigured','resolver_module_restored')
    foreach($taskReceipt in @($taskController,$taskChild)){
        if(@($taskReceipt.adapter_state.PSObject.Properties).Count -ne 5){$taskValid=$false}
        foreach($taskName in $taskStateNames){if($taskReceipt.adapter_state.$taskName -isnot [bool] -or $taskReceipt.adapter_state.$taskName -cne $true){$taskValid=$false}}
    }
    $taskAuthorityEvents=@('generated_release','generated_admit','generated_bind','owned_start_validated','worker_start_bound')
    if(@($taskResult.authority_events).Count -ne 5){$taskValid=$false}
    for($taskIndex=0;$taskIndex -lt 5;$taskIndex++){if($taskResult.authority_events[$taskIndex] -cne $taskAuthorityEvents[$taskIndex]){$taskValid=$false}}
    if($taskResult.actual_adapter_context -cne 'faster_whisper_session' -or $taskResult.binding_calls -ne 1){$taskValid=$false}
    foreach($taskField in @('adapter_globals_restored','real_resolver_approval_unchanged_none','actual_factory_and_permit','adapter_owned_cleanup')){
        if($taskResult.$taskField -isnot [bool] -or $taskResult.$taskField -cne $true){$taskValid=$false}
    }
    if($taskChild.result.real_resolver_approval_unchanged_none -cne $true -or $taskChild.result.real_resolver_functions_unchanged -cne $true){$taskValid=$false}
    $taskExpectedPolicy=[ordered]@{
        action='bind_generated_adapter_start';choice='large-v3-turbo';compute_type='int8';constructor_called=$false;device='cpu';generated_only=$true
        generated_root=$taskRun;inherited_manifest_sha256=$taskResult.manifest_sha256;local_files_only=$true
        namespace_sha256='NAMESPACE_SHA';profile_id='generated-asr-reliability-v1';real_runtime_approved=$false
        recipe_sha256='RECIPE_SHA';revision='REVISION';usage='reliability'
    }
    $taskPolicyCanonical=$taskExpectedPolicy | ConvertTo-Json -Compress -Depth 5
    $taskPolicyDigest=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::ASCII.GetBytes($taskPolicyCanonical))).ToLowerInvariant()
    foreach($taskObserved in @($taskResult,$taskChild.result)){
        if(@($taskObserved.adapter_start.PSObject.Properties).Count -ne $taskExpectedPolicy.Count){$taskValid=$false}
        foreach($taskName in $taskExpectedPolicy.Keys){
            $taskValue=$taskObserved.adapter_start.$taskName
            $taskExpected=$taskExpectedPolicy[$taskName]
            if($null -eq $taskValue -or $taskValue.GetType() -ne $taskExpected.GetType() -or $taskValue -cne $taskExpected){$taskValid=$false}
        }
        $taskAck=$taskObserved.adapter_start_ack
        if(@($taskAck.PSObject.Properties).Count -ne 3 -or $taskAck.action -cne 'generated_adapter_start_bound' -or $taskAck.policy_sha256 -cne $taskPolicyDigest -or ($taskAck.model_calls -isnot [long] -and $taskAck.model_calls -isnot [int]) -or $taskAck.model_calls -ne 0){$taskValid=$false}
    }
'''.replace('NAMESPACE_SHA',namespace_sha).replace('RECIPE_SHA',recipe_sha).replace('REVISION',revision)
launch=launch.replace('}catch{$taskValid=$false;$taskReceiptError=$_.Exception.GetType().Name}',checks+'}catch{$taskValid=$false;$taskReceiptError=$_.Exception.GetType().Name}')
a='# BEGIN EXACT NATIVE RECEIPT BLOCK';b='# END EXACT NATIVE RECEIPT BLOCK'
assert launch.split(a)[1].split(b)[0]==old_launch.split(a)[1].split(b)[0]
put('run_actual_adapter01.ps1',launch);diff('launcher.diff',old_launch,launch)
admission={'root_reviewed':False,'scope':'generated-actual-asr-adapter-only','case':'positive','operation_mode':'drain','run_path':RUN,
           'source_inputs_sha256':sha(map_text.encode()),'launcher_sha256':sha(launch.encode()),'real_runtime_approval':False,
           'model_calls_authorized':False,'new_native_apis':[]}
put('ROOT-ADMISSION-drain.template.json',json.dumps(admission,indent=2)+'\n')
result={'candidate_executions':0,'source_count':12,'support_count':9,'native_api_count':32,
        'original_audit_ffi_monitor_finder_finalizer_ast_unchanged':True,'original_native_exit_block_unchanged':True,
        'bridge_source_unchanged':sha(bridge_raw),'bootstrap_sha256':sha(boot.encode()),'launcher_sha256':sha(launch.encode()),
        'source_map_sha256':sha(map_text.encode()),'recipe_sha256':recipe_sha,'namespace_sha256':namespace_sha,'run_path':RUN}
put('PREPARATION-BINDINGS.json',json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
