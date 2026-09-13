from pathlib import Path
import subprocess,sys
root=Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
tree=root / '_scratch/wheel-integrator13'
before=root / '_scratch/nltk-wheel-original-probes13'
saved=root / '_scratch/nltk-wheel-probe-correction13'
saved.mkdir(exist_ok=False)
for name,base in [('takeover',tree),('archived-original',before)]:
    path=base / 'tests/test_nltk_wheel_boundaries.py'
    raw=path.read_text(encoding='utf8');(saved/(name+'-before.py.txt')).write_bytes(path.read_bytes())
    assert "monkeypatch.setattr(Path, 'lstat', denied)" in raw
    raw=raw.replace("monkeypatch.setattr(Path, 'lstat', denied)","monkeypatch.setattr(builder.os, 'lstat', denied)")
    path.write_text(raw,encoding='utf8',newline='\n')
(saved / 'reason.txt').write_text('Astra worker01: 41 pass / two fail. Restore the existing path-traversal error wording in production. The new unaccepted filesystem probe patched Path.lstat, but this builder calls os.lstat. Correct that mock receiver in both negative and repaired probes; the permission-refusal assertion stays unchanged. The old source still swallows the now-exercised permission failure. Prior probe source and results are preserved. No committed test changed.\n',encoding='utf8')
subprocess.run([sys.executable,'-I','-S','-B',str(root / '_scratch/run_media_verify12.py'),
                '--root',str(before),'--label','original02','tests/test_nltk_wheel_boundaries.py'],cwd=root)
