"""Inventory generated files after Setup, before any helper runs."""
import datetime as dt,hashlib,json,re,stat
from pathlib import Path
r=Path(__file__).resolve().parents[1]
root=Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 08')
app=root/'app';out=root/'installed-generated-files.json'
assert app.is_dir() and not out.exists()
seal=r/'docs/library/proof/candidate-package-08-2026-09-12'
expected={x['path'] for x in json.loads((seal/'staged-inventory.json').read_text())['files'] if x['install_role']=='installed'}
files=[];extras=[]
for q in app.rglob('*'):
 assert not q.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT,q
 if not q.is_file():continue
 name=q.relative_to(app).as_posix();files.append(name)
 if name in expected:continue
 with q.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
 extras.append({'path':name,'bytes':q.stat().st_size,'sha256':digest,'recognized_generated_name':name=='isolated-install.json' or bool(re.fullmatch(r'unins\d{3}\.(?:exe|dat|msg)',name))})
report={'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'scope':'Inventory immediately after Setup/reinstall, before the installed helper; generated names are reviewed against actual Inno logs, not treated as signed binaries','app':str(app),'actual_files':len(files),'expected_installed_files':len(expected),'missing_expected':sorted(expected-set(files)),'extra_files':extras,'unrecognized_extra_files':[row for row in extras if not row['recognized_generated_name']]}
out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps(report,indent=2))
raise SystemExit(1 if report['missing_expected'] or report['unrecognized_extra_files'] else 0)
