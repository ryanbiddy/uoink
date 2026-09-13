from pathlib import Path
import subprocess,sys
root=Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
source=(root / '_scratch/review_nltk_wheel13.py').read_text(encoding='utf8')
source=source.replace("worker=Path(r'C:\\Users\\hello\\AppData\\Local\\AgentControlRoom\\worktrees\\uoink-library\\a332397f-bac\\gemini')","worker=root / '_scratch/wheel-integrator13'")
source=source.replace("out=root / '_scratch/nltk-wheel-astra-artifact01'","out=root / '_scratch/nltk-wheel-astra-artifact02'")
source=source.replace('Provisional worker artifact, independently inspected before worker completion; no packaging utility or NLTK execution.','Repaired stored wheel, independently inspected after both-root tests; no packaging utility or NLTK execution.')
source=source.replace("patched,pmeta=inspect(local,'nltk-3.10.3+uoink.pathsec1.dist-info')", "patched,pmeta=inspect(local,'nltk-3.10.3+uoink.pathsec1.dist-info')\nwith zipfile.ZipFile(io.BytesIO(local)) as stored:\n    assert all(i.compress_type==zipfile.ZIP_STORED and i.create_system==3 and i.date_time==(2026,9,12,0,0,0) for i in stored.infolist())\nassert hashlib.sha256(local).hexdigest()=='969f623541344ade83ea267130e016d6cb8a223ecaaf28fb3d7a663c7e3c60d8'")
target=root / '_scratch/review_nltk_wheel13_final.py'
with target.open('x',encoding='utf8') as stream:stream.write(source)
raise SystemExit(subprocess.run([sys.executable,'-I','-S','-B',str(target)],cwd=root).returncode)
