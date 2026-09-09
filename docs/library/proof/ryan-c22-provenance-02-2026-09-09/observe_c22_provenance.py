"""Narrow original bundled provenance check after the documented command/guard repair."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
r=Path(__file__).resolve().parents[1];o=r/'_scratch/c22-provenance-02';o.mkdir(exist_ok=False)
source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip()
assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=r,text=True).strip()
app=r/'installer/staging';guard=app/'python/Lib/site-packages/sitecustomize.py';assert not guard.exists()
pth=app/'python/python311._pth';before=pth.read_bytes()
for key in ('ANTHROPIC_API_KEY','OPENAI_API_KEY','XAI_API_KEY','GROK_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY'):os.environ.pop(key,None)
os.environ['IG_FORBIDDEN_LIVE']=r'C:\Users\hello\AppData\Local\Uoink\index.db'
for key in ('USERPROFILE','LOCALAPPDATA','APPDATA','TEMP','TMP'):
 q=o/'environment'/key;q.mkdir(parents=True);os.environ[key]=str(q)
sys.path.insert(0,str(r/'scripts'))
from install_receipt.runner import OperatorRunner
from install_receipt.launcher import run_provenance_command
from install_receipt.oracles import modules_inside_app
package=json.loads((r/'docs/library/proof/candidate-package-02-2026-09-09/package-manifest.json').read_text(encoding='utf8'))
runner=OperatorRunner.create(receipt_root=o/'receipt',installed_app_path=app,package_path=r/'build'/package['package_name'],
 package_sha256=package['package_sha256'],isolated_profile=o/'receipt/profiles/empty',isolated_port=18351,
 synthetic=True,require_space=False,require_bundled_python=True,skip_ordinary_user_check=True)
(o/'receipt/profiles/empty').mkdir(exist_ok=True)
result=run_provenance_command(runner,app)
report={'source':source,'scope':'Original old-package bundled imports only; no helper/Setup/client/model','result':result,
 'module_containment':modules_inside_app(result.get('structured'),app),'guard_absent_after':not guard.exists(),'pth_unchanged':before==pth.read_bytes()}
(o/'observation.json').write_text(json.dumps(report,indent=2,default=str)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k!='result'}|{'exit':result['exit'],'structured_ok':result['structured_ok'],'imports':(result.get('structured') or {}).get('import_errors'),'mcp':(result.get('structured') or {}).get('mcp_version')},indent=2))
raise SystemExit(0 if result['structured_ok'] and report['module_containment']['ok'] and report['guard_absent_after'] and report['pth_unchanged'] else 1)
