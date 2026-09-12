"""Preflight and seal explicit installed evidence; never export databases or auth stores."""
from pathlib import Path
import hashlib,json,os,re,stat
repo=Path(__file__).resolve().parents[1];scratch=repo/'_scratch'
root=Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 08')
prior=Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 07\uninstall-before-package08-2026-09-12')
out=repo/'docs/library/proof/ryan-agent-installed-08-2026-09-12'
summary=json.loads((scratch/'installed08-reviewed-summary.json').read_text())
assert summary['setup_observed'] and summary['actual_client_tool_calls']==summary['successful_terminal_hooks'] and summary['failed_terminal_hooks']==0
sources={}
def add(p,name):
    assert p.is_relative_to(root) or p.is_relative_to(prior) or p.is_relative_to(scratch)
    assert not p.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
    assert 'claude-config' not in p.parts and 'claude-debug' not in p.name
    assert not any(x in p.name.lower() for x in ('.db','credentials','token.txt','signin-'))
    assert name not in sources and not Path(name).is_absolute() and '..' not in Path(name).parts
    data=p.read_bytes()
    if p.suffix.lower() not in ('.png','.jpg','.jpeg','.webp','.bin'):
        assert not re.search(rb'sk-ant-[A-Za-z0-9_-]{20,}',data),name
        assert not re.search(rb'"(?:access_token|refresh_token)"\s*:\s*"[^"\r\n]{12,}"',data),name
    sources[name]=(p,data)
def tree(folder,label,extensions):
    for base,dirs,files in os.walk(folder):
        dirs[:]=[name for name in dirs if name not in ('claude-config','tmp','__pycache__','guard-canary')]
        for name in dirs:assert not (Path(base)/name).lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
        for name in files:
            p=Path(base)/name
            if any(x in name.lower() for x in ('.db','credentials','token.txt','claude-debug','signin-')):continue
            if p.suffix.lower() in extensions or name in ('stdout','stderr','protected-sentinel.bin'):
                add(p,label+'/'+p.relative_to(folder).as_posix())
for p in root.iterdir():
    if p.is_file() and p.suffix in ('.json','.stdout','.stderr','.log','.inf'):add(p,'observation/'+p.name)
add(root/'app/isolated-install.json','observation/installed-marker.json')
for stage in ('install','same-version-reinstall'):
    add(root/(stage+'-temp')/'uoink-install-verify.log','observation/'+stage+'-files-only.log')
for p in prior.iterdir():
    if p.is_file() and p.suffix in ('.json','.log'):add(p,'prior-isolated-uninstall/'+p.name)
c22=root/'c22'
for p in c22.iterdir():
    if p.is_file() and (p.suffix=='.json' or p.name=='journal.jsonl'):add(p,'c22/'+p.name)
for folder in ('commands','evidence','artifacts'):
    tree(c22/folder,'c22/'+folder,{'.json','.jsonl','.log','.png','.jpg','.txt','.stdout','.stderr'})
for p in (c22/'profiles').glob('*/c22-guard-events.jsonl'):add(p,'c22/'+p.relative_to(c22).as_posix())
tree(root/'p4','p4',{'.json','.jsonl','.stdout','.stderr','.png','.jpg','.txt','.diff','.py','.md'})
tree(root/'p6-published01','p6-published01',{'.json','.jsonl','.stdout','.stderr','.png','.jpg','.txt','.diff','.py','.md','.log'})
for folder,label in (('decoder-probe-02','decoder-probe'),('codec-probe-02','codec-probe')):
    tree(root/folder,label,{'.json','.png','.jpg','.webp'})
instruments=['agent_receipt_observe06.py','agent_install_observer05.ps1','uninstall_retained_package07.ps1','uninstall_retained_package07.diff',
    'check_installed_package_inputs.py','package_decoder_probe.py','installed_codec_probe.py',
    'inventory_installed_extras08.py','run_installed_decoders08.py','run_installed_decoders08_portable.py',
    'complete_browser08.py','review_browser08.py','agent-browser08.json','run_browser08.py','freeze_client08_inputs.py',
    'run_installed_client08.py','p4_operator_client08.py','review_client08.py','prepare_native08.py',
    'p4_operator_native_reshelve0108.py','run_native_reshelve0108.py','p4_operator_native_consult0108.py','run_native_consult0108.py',
    'p4_operator_native_reshelve0108.py.diff','run_native_reshelve0108.py.diff','p4_operator_native_consult0108.py.diff','run_native_consult0108.py.diff',
    'review_native08.py','published_chapter08.py','observe_published_chapter08.py','review_published08_02.py',
    'prepare_collection08.py','review_installed08.py','seal_installed08.py',
    'package08-instrument-adaptations.json','package08-final-source-rebinding.json',
    'installed08-aggregate-preexecution-review.json','review_installed08.py.preexecution.diff',
    'prepare_delivery08.py','seal_installed08.py.diff']
for name in instruments:add(scratch/name,'instruments/'+name)
add(scratch/'installed08-reviewed-summary.json','summary.json')
# Compare against only explicitly disposable receipt tokens. Never inspect auth stores.
tokens=[]
for p in [*(c22/'profiles').glob('*/token.txt'),root/'p4/profile/token.txt',root/'p6-published01/profile/token.txt']:
    if p.is_file():
        value=p.read_bytes().strip()
        if len(value)>=16:tokens.append(value)
for name,(p,data) in sources.items():
    if p.suffix.lower() not in ('.png','.jpg','.jpeg','.webp','.bin'):
        assert all(token not in data for token in tokens),'Disposable token in export: '+name
out.mkdir(exist_ok=False);(out/'.gitattributes').write_bytes(b'* -text\n')
for name,(p,data) in sorted(sources.items()):
    target=out/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
files={p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file()}
manifest={'scope':'Same-account isolated installed observations; original partial/pending statuses retained. Explicit private-data exclusions. Actual client records and synthetic instrument probes remain separately labeled.',
          'files':files}
with (out/'SHA256.json').open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'payloads':len(files),'setup_exits':summary['setup_exits'],'c22':summary['c22_raw_counts'],'p4':summary['p4_raw_counts'],'client_calls':summary['actual_client_tool_calls'],'release_ready':False},indent=2))
