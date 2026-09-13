import importlib.util,json,shutil,subprocess
from pathlib import Path
root=Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
spec=importlib.util.spec_from_file_location('nltk_source_guard',root / 'scripts/prepare_nltk_pathsec_backport.py')
guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
source=guard.safe_local_path(root / 'installer/staging/python/Lib/site-packages/nltk')
out=guard.validate_destination_boundary(root / '_scratch/nltk-upstream-before-local13',source)
before=guard.tree_hashes(source)
assert (source / 'VERSION').read_text().strip()=='3.10.3'
for rel,digest in guard.EXPECTED_ORIGINAL_HASHES.items():assert before[Path(rel).as_posix()]==digest
out.mkdir(exist_ok=False)
shutil.copytree(source,out / 'nltk',symlinks=True)
assert guard.tree_hashes(out/'nltk')==before==guard.tree_hashes(source)
(out / 'receipt.json').write_text(json.dumps({'source':str(source),'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
 'fixture':str(out/'nltk'),'files':before,'source_unchanged':True,'models_loaded':False},indent=2)+'\n',encoding='utf8')
print(json.dumps({'preserved_files':len(before),'fixture':str(out/'nltk'),'source_unchanged':True}))
