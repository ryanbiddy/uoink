from pathlib import Path
import shutil,json,hashlib
r=Path(__file__).resolve().parents[1];o=r/'_scratch/dependency-resolve-03';o.mkdir(exist_ok=False)
runtime=o/'python';runtime.mkdir()
src=r/'installer/staging/python'
for name in ['python.exe','python311.zip']+[p.name for p in src.iterdir() if p.suffix.lower() in ('.pyd','.dll')]:
 if (src/name).is_file():shutil.copyfile(src/name,runtime/name)
(runtime/'python311._pth').write_text('python311.zip\n.\nimport site\n',encoding='utf8')
lock=(r/'requirements-installer-lock.txt').read_text(encoding='utf8')
for name,old,new in [('pillow','10.4.0','12.3.0'),('nltk','3.10.0','3.10.3'),('cryptography','49.0.0','50.0.1'),('mcp','1.27.1','1.28.1')]:
 assert lock.count(name+'=='+old)==1
 lock=lock.replace(name+'=='+old,name+'=='+new)
(o/'proposed-lock.txt').write_text(lock,encoding='utf8')
(o/'preflight.json').write_text(json.dumps({'source':'c7a8426','kind':'disposable Python 3.11 metadata resolution; no product import/install','copied_runtime':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in runtime.iterdir() if p.is_file()},'new_lock_sha256':hashlib.sha256((o/'proposed-lock.txt').read_bytes()).hexdigest()},indent=2)+'\n',encoding='utf8')
