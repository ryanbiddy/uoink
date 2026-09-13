"""Bind exact source text and compare connected prefixes; no candidate import."""
from pathlib import Path
import ast
import difflib
import hashlib
import json
BASE=Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
HERE=Path(__file__).parent
OLD=BASE/'_scratch/generated-operation-native-proposal01'
mapping=json.loads((OLD/'SOURCE-INPUTS.json').read_bytes())
paths=dict(mapping['source_paths'])
hashes=dict(mapping['source_sha256'])
paths['asr_loading_adapter.py']=str(BASE/'_scratch/asr-permit-facade-proposal01/asr_loading_adapter.py')
hashes['asr_loading_adapter.py']='2b6cbbad24264423e520bac54b7c2fb4c40ae771e5c15b08381dac1d2228a63c'
paths['trusted_asr_resolver.py']=str(BASE/'_scratch/asr-trusted-manifest-resolver-proof02/proposal/trusted_asr_resolver.py')
hashes['trusted_asr_resolver.py']='16a5a1245f649a3eb04d077b661835503f08bef0ff8822dcb545176f0cc30833'
rows=[]
for name,path in paths.items():
    raw=Path(path).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==hashes[name]
    ast.parse(raw)
    rows.append({'name':name,'path':path,'bytes':len(raw),'sha256':hashes[name]})
raw=(HERE/'generated_adapter_flow.py').read_bytes()
tree=ast.parse(raw)
old_raw=Path(paths['generated_operation_flow.py']).read_bytes()
old_tree=ast.parse(old_raw)
for function in ('controller_flow','child_flow'):
    original=next(n for n in old_tree.body if isinstance(n,ast.FunctionDef) and n.name==function)
    current=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==function)
    before=ast.get_source_segment(old_raw.decode(),original)+'\n'
    after=ast.get_source_segment(raw.decode(),current)+'\n'
    with (HERE/(function+'-connection.diff')).open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),
            fromfile='generated_operation_flow.py:'+function,tofile='generated_adapter_flow.py:'+function)))
calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call)]
assert not any(isinstance(n.func,ast.Attribute) and n.func.attr=='open_owned_session' for n in calls)
factory=[n for n in calls if isinstance(n.func,ast.Name) and n.func.id=='OwnedRuntimeFactory']
assert len(factory)==1 and ast.unparse(factory[0])=='OwnedRuntimeFactory(port.lifecycle)'
context=[n for n in calls if isinstance(n.func,ast.Attribute) and n.func.attr=='faster_whisper_session']
assert len(context)==1
value={'schema':'uoink.generated-actual-adapter-source.v1','candidate_executions':0,
       'candidate_sha256':hashlib.sha256(raw).hexdigest(),'candidate_bytes':len(raw),
       'prior_operation_preparation_manifest_sha256':hashlib.sha256((OLD/'PREPARATION-MANIFEST.json').read_bytes()).hexdigest(),
       'inherited_source_bindings':rows,'factory':'actual OwnedRuntimeFactory(port.lifecycle)',
       'context':'actual adapter.faster_whisper_session','direct_open_owned_session_calls_in_bridge':0,
       'new_native_apis':[],'real_authority_granted':False,'future_native_source_count':12}
with (HERE/'SOURCE-BINDINGS.json').open('x',encoding='utf-8',newline='\n') as stream:
    stream.write(json.dumps(value,indent=2)+'\n')
print(json.dumps({'candidate_sha256':value['candidate_sha256'],'candidate_bytes':len(raw),'bound_existing_sources':len(rows),'candidate_executions':0}))
