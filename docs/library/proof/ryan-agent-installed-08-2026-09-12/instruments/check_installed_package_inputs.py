"""Compare every sealed compiler input with actual installed files; never start product code."""
import argparse,datetime as dt,hashlib,json,stat
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--seal',required=True,type=Path);p.add_argument('--app',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
root=Path(r'E:\AI\projects\uoink\installation-receipts').resolve();app=a.app.resolve();out=a.out.resolve()
assert app.is_relative_to(root) and out.is_relative_to(root) and not out.exists()
inventory=json.loads((a.seal/'staged-inventory.json').read_text(encoding='utf8'));rows=[];failures=[];compiler_only=[]
for row in inventory['files']:
 role=row.get('install_role','installed')
 if role!='installed':
  assert (role=='installer-only' and row['path']=='upgrade_prep.ps1') or (role=='compiler-resource' and row['path'].startswith('installer-assets/wizard-') and row['path'].endswith('.bmp')),row
  compiler_only.append(row);continue
 q=app/row['path'];resolved=q.resolve();assert resolved.is_relative_to(app)
 if not q.is_file():failures.append({'path':row['path'],'error':'missing'});continue
 assert not q.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
 with q.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
 observed={'path':row['path'],'bytes':q.stat().st_size,'sha256':digest}
 observed['matches']=observed['bytes']==row['bytes'] and digest==row['sha256'];rows.append(observed)
 if not observed['matches']:failures.append(observed)
report={'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'scope':'Actual installed bytes compared with every sealed Inno Files destination; setup-only inputs separately accounted; registry/shortcut effects and runtime checks are separate','app':str(app),'build_source':inventory['build_source'],'compared':len(rows),'expected_installed':len(inventory['files'])-len(compiler_only),'compiler_only':compiler_only,'total_compiler_inputs':len(inventory['files']),'failures':failures,'files':rows}
out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({k:v for k,v in report.items() if k!='files'},indent=2));raise SystemExit(1 if failures else 0)
