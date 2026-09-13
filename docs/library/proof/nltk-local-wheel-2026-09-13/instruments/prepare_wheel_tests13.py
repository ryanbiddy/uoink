from pathlib import Path
import shutil,subprocess,sys
root=Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
tree=root / '_scratch/wheel-integrator13'
original=root / '_scratch/nltk-wheel-worker-original13'
before=root / '_scratch/nltk-wheel-original-probes13'
before.mkdir(exist_ok=False)
for rel,base in [('scripts/build_nltk_pathsec_wheel.py',original),('tests/test_nltk_wheel_boundaries.py',tree)]:
    p=before / rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((base / rel).read_bytes())
test=tree / 'tests/test_nltk_local_wheel.py'
raw=test.read_text(encoding='utf8')
old='''def test_nltk_not_imported() -> None:
    """Invariant: NLTK module must never be imported in memory."""
    assert "nltk" not in sys.modules, "NLTK module unexpectedly imported in test session"'''
new='''def test_nltk_not_imported() -> None:
    """Observe this utility in a fresh child, independent of other test imports."""
    import subprocess
    code = "import importlib.util,sys; s=importlib.util.spec_from_file_location('wheel_builder',sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); assert 'nltk' not in sys.modules"
    subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code, str(BUILD_SCRIPT)], check=True)'''
assert old in raw;raw=raw.replace(old,new)
raw=raw.replace('11c885646a44e22fe515b1e487d74b87f82922a580b96d7c3b2a6bc5ead1ccb0','969f623541344ade83ea267130e016d6cb8a223ecaaf28fb3d7a663c7e3c60d8')
raw=raw.replace('1799214','6597605')
test.write_text(raw,encoding='utf8',newline='\n')
result=subprocess.run([sys.executable,'-I','-S','-B',str(root/'_scratch/run_media_verify12.py'),
                       '--root',str(before),'--label','original01','tests/test_nltk_wheel_boundaries.py'],cwd=root)
print('Original negative baseline exit:',result.returncode)
