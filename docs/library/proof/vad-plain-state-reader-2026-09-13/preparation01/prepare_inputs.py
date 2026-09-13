"""Copy/hash reviewed text and derive static case membership; never execute proposals."""
import ast
from datetime import datetime,timezone
import difflib
import hashlib
import json
import math
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
sha=lambda raw:hashlib.sha256(raw).hexdigest()
def save(name,value):
    with (OUT/name).open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(json.dumps(value,indent=2)+'\n')
sources=[('fixed-plan.json','_scratch/vad-fixed-converter-proposal01/fixed-plan.json',
    '37af25ab777ca7c322e00bec20dfffc1b6959d32c5bbd1a8c678bfc4126c91bf'),
    ('context/fixed_converter.py.txt','_scratch/vad-fixed-converter-proposal01/fixed_converter.py',
    'b31915b2e6d78a29ec05699952e5e0bfa01d234fec31ed37481c21665cfba54b'),
    ('context/fixed-factory.proposal.txt','_scratch/vad-selected-metadata-map01/fixed-factory.proposal.txt',
    '69136c1f7d5cd7bf283e3634dff730c9fd951a314a80b0fa134208f3d1c1820b')]
bindings=[]
for copy_name,relative,digest in sources:
    source=ROOT/relative;raw=source.read_bytes();assert sha(raw)==digest
    target=OUT/copy_name;target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as stream:stream.write(raw)
    bindings.append({'source':str(source),'copy':copy_name,'bytes':len(raw),'sha256':digest,
        'executed':False})
raw_brief=(ROOT/'docs/library/VAD-PLAIN-STATE-READER-PROPOSAL-BRIEF-2026-09-13.md').read_bytes()
(OUT/'context/root-brief.md').write_bytes(raw_brief)
bindings.append({'source':str(ROOT/'docs/library/VAD-PLAIN-STATE-READER-PROPOSAL-BRIEF-2026-09-13.md'),
    'copy':'context/root-brief.md','bytes':len(raw_brief),'sha256':sha(raw_brief),'executed':False})
plan=json.loads((OUT/'fixed-plan.json').read_text(encoding='utf-8-sig'))
rows=sorted(plan['rows'],key=lambda row:row['key'])
assert len(rows)==54 and sum(math.prod(row['shape']) for row in rows)==1472999
header={};offset=0
for row in rows:
    end=offset+math.prod(row['shape'])*4
    header[row['key']]={'dtype':'F32','shape':row['shape'],'data_offsets':[offset,end]}
    offset=end
assert offset==5891996
encoded=json.dumps(header,ensure_ascii=True,sort_keys=True,separators=(',', ':'),allow_nan=False).encode('utf-8')
encoded+=b' '*(-len(encoded)%8)
save('CANONICAL-LAYOUT.json',{'schema':'exact frozen converter output constraints',
    'plan_sha256':sources[0][2],'tensor_count':54,'dense_elements':1472999,'dense_bytes':offset,
    'canonical_header_bytes':len(encoded),'canonical_header_sha256':sha(encoded),
    'whole_output_bytes':8+len(encoded)+offset,'header':header,'artifact_exists':False})
save('SOURCE-BINDINGS.json',{'captured_utc':datetime.now(timezone.utc).isoformat(),
    'sources':bindings,'actual_asset_read':False,'proposal_source_executed':False})

reader_tree=ast.parse((OUT/'plain_state_reader.py').read_text(encoding='utf-8'))
factory_text=(OUT/'context/fixed-factory.proposal.txt').read_text(encoding='utf-8')
factory_code=factory_text.split('----- BEGIN PROPOSED PYTHON (TEXT ONLY) -----')[1].split('----- END PROPOSED PYTHON -----')[0]
factory_tree=ast.parse(factory_code)
reader_shapes=next(node for node in reader_tree.body if isinstance(node,ast.FunctionDef) and node.name=='_fixed_shapes')
factory_shapes=next(node for node in factory_tree.body if isinstance(node,ast.FunctionDef) and node.name=='_fixed_shapes')
assert ast.literal_eval(reader_shapes.body[0].value)==ast.literal_eval(factory_shapes.body[0].value)
assert ast.dump(reader_shapes.body[1],include_attributes=False)==ast.dump(factory_shapes.body[1],include_attributes=False)
harness_tree=ast.parse((OUT/'qualify_reader.py').read_text(encoding='utf-8'))
case_names=[]
for statement in harness_tree.body:
    if isinstance(statement,ast.FunctionDef):
        for decorator in statement.decorator_list:
            if isinstance(decorator,ast.Call) and isinstance(decorator.func,ast.Name) and decorator.func.id=='case':
                case_names.append(ast.literal_eval(decorator.args[0]))
    elif isinstance(statement,ast.For):
        calls=[node for node in ast.walk(statement) if isinstance(node,ast.Call)
            and isinstance(node.func,ast.Name) and node.func.id=='parameter_case']
        if not calls:continue
        assert len(calls)==1 and isinstance(statement.iter,ast.List)
        expression=calls[0].args[0]
        assert isinstance(expression,ast.BinOp) and isinstance(expression.op,ast.Add)
        prefix=ast.literal_eval(expression.left)
        for item in statement.iter.elts:
            assert isinstance(item,ast.Tuple)
            case_names.append(prefix+ast.literal_eval(item.elts[0]))
assert case_names and len(case_names)==len(set(case_names))
save('EXPECTED-CASES.json',case_names)
save('INPUTS.json',{'child_files':{name:sha((OUT/name).read_bytes()) for name in
    ('plain_state_reader.py','qualify_reader.py','fixed-plan.json')},
    'scope':'Only locally generated synthetic bytes under separately reviewed harness authority'})
launch_tree=ast.parse((OUT/'launch.py').read_text(encoding='utf-8'))
required=('plain_state_reader.py','qualify_reader.py','fixed-plan.json','INPUTS.json',
    'launch.py','BRIEF.md','SOURCE-BINDINGS.json','EXPECTED-CASES.json',
    'context/fixed_converter.py.txt','context/fixed-factory.proposal.txt')
save('ROOT-ADMISSION.TEMPLATE.json',{'root_reviewed':False,'review_document':'ROOT MUST RECORD EXACT SOURCE/HARNESS/LAUNCHER REVIEW',
    'scope':'generated-synthetic-plain-state-only','label':'vpr01',
    'source_hashes':{name:sha((OUT/name).read_bytes()) for name in required}})
for before,after,name in [
    ('drafts/plain_state_reader-before-profile-budget-review.py','plain_state_reader.py','reader-prequalification.patch'),
    ('drafts/qualify_reader-before-lexical-prefix-review.py','qualify_reader.py','guard-prequalification.patch')]:
    raw_before=(OUT/before).read_text(encoding='utf-8');raw_after=(OUT/after).read_text(encoding='utf-8')
    with (OUT/name).open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(''.join(difflib.unified_diff(raw_before.splitlines(keepends=True),raw_after.splitlines(keepends=True),fromfile=before,tofile=after)))
save('STATIC-PREPARATION.json',{'python_parsed_only':['plain_state_reader.py','qualify_reader.py','launch.py'],
    'factory_base_shape_literal_and_lstm_loop_ast_match':True,'expected_case_count':len(case_names),
    'reader_harness_factory_or_converter_executed':False,'real_approval':False,
    'canonical_output_bytes':8+len(encoded)+offset})
with (OUT/'.gitattributes').open('x',encoding='ascii',newline='\n') as stream:stream.write('* -text\n')
print(json.dumps({'prepared_case_count':len(case_names),'canonical_header_bytes':len(encoded),
    'canonical_output_bytes':8+len(encoded)+offset,'executed_proposals':False,
    'source_hashes':{name:sha((OUT/name).read_bytes()) for name in
        ('plain_state_reader.py','qualify_reader.py','launch.py','run-root.ps1','BRIEF.md')}}))
