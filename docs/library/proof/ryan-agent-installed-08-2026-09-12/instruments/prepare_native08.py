"""Freeze two bounded native-prompt observations without modifying prepared files."""
from pathlib import Path
import ast,datetime as dt,difflib,hashlib,json,uuid
r=Path(__file__).resolve().parents[1];scratch=r/'_scratch'
root=Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 08')
profile=root/'p4/profile';client=profile/'client'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
prep=json.loads((client/'client-config-preparation.json').read_text())
for name,digest in prep['hashes'].items():assert sha(client/name)==digest
preview=json.loads((profile/'prompt-preparation.json').read_text())['preview']
assert preview['expires_ms']>dt.datetime.now(dt.timezone.utc).timestamp()*1000+60000
rows=[]
for label,prompt in [('native-reshelve01','/mcp__uoink__reshelve-review '+preview['preview_id']+'\n'),
                     ('native-consult01','/mcp__uoink__consult-library fixture\n')]:
    session=str(uuid.uuid4())
    base=scratch/'p4_operator_client08.py';old=base.read_text()
    new=old.replace('stage_name = args.stage + ("-" + args.client_route if args.stage == "client" else "")',
                    'stage_name = args.stage + ("-" + args.client_route if args.stage == "client" else "") + "-'+label+'"',1)
    needle='        command = [str(args.client_exe), *launch["args"], "--print", "--verbose",'
    assert new.count(needle)==1
    new=new.replace(needle,'        launch["args"][launch["args"].index("--session-id") + 1] = '+repr(session)+'\n'+needle,1)
    adapter=scratch/('p4_operator_'+label.replace('-','_')+'08.py')
    with adapter.open('x',encoding='utf8',newline='\n') as f:f.write(new)
    ast.parse(new)
    patch=adapter.with_suffix('.py.diff');patch.write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile=base.name,tofile=adapter.name)),encoding='utf8')
    base=scratch/'run_installed_client08.py';old=base.read_text();new=old
    new=new.replace("a = p.parse_args()","a = p.parse_args()\nassert a.route == 'ordinary'",1)
    new=new.replace("f'client-{a.route}-observation01.json'",repr(label+'-observation.json'))
    new=new.replace("f'p4/{a.route}-request.txt'",repr('p4/'+label+'-request.txt'))
    new=new.replace("'_scratch/p4_operator_client08.py'",repr('_scratch/'+adapter.name))
    new=new.replace("f'client-{a.route}-driver01.stdout'",repr(label+'-driver.stdout'))
    new=new.replace("f'client-{a.route}-driver01.stderr'",repr(label+'-driver.stderr'))
    outer=scratch/('run_'+label.replace('-','_')+'08.py')
    with outer.open('x',encoding='utf8',newline='\n') as f:f.write(new)
    ast.parse(new)
    patch2=outer.with_suffix('.py.diff');patch2.write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile=base.name,tofile=outer.name)),encoding='utf8')
    path=root/('p4/'+label+'-request.txt')
    with path.open('x',encoding='utf8',newline='\n') as f:f.write(prompt)
    rows.append({'label':label,'session':session,'request_sha256':sha(path),'files':{p.name:sha(p) for p in (adapter,outer,patch,patch2)}})
for name,digest in prep['hashes'].items():assert sha(client/name)==digest
record={'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'native_prompt_observations':rows,
        'prepared_files_unchanged':len(prep['hashes']),'preview_expires_ms':preview['expires_ms'],
        'review':'Fresh names and session ids only; same guarded original package route, auth overlay and permissions. No original fixture edits or preview renewal.',
        'model_started':False}
with (root/'p4/native08-preexecution-review.json').open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
