import hashlib,json,zipfile
from pathlib import Path
r=Path(__file__).resolve().parents[1];archive=r/'build/Uoink-Living-Library-3-8-0-Review-Kit-05-2026-09-10.zip'
out=r/'_scratch/reviewkit05-extracted';out.mkdir(exist_ok=False)
with zipfile.ZipFile(archive) as z:
 names=z.namelist();assert len(names)==len(set(name.casefold() for name in names))
 for name in names:
  target=(out/name).resolve();assert target.is_relative_to(out) and target!=out
 z.extractall(out)
manifest=json.loads((out/'BUNDLE-SHA256.json').read_text(encoding='utf8'))
for name,expected in manifest['files'].items():
 q=out/name
 with q.open('rb') as f:observed=hashlib.file_digest(f,'sha256').hexdigest()
 assert q.stat().st_size==expected['bytes'] and observed==expected['sha256'],name
state=json.loads((out/'release-state.json').read_text(encoding='utf8'))
assert state['release_ready'] is False and state['published'] is False
assert not any('PRODUCT-SUITE-REVIEW' in name or 'project-state.json' in name for name in names)
record={'status':'PASS','payloads':len(manifest['files']),'safe_paths':True,'case_insensitive_collisions':False,'all_extracted_hashes_match':True,'release_ready':state['release_ready'],'private_suite_inventory_included':False,'bundle_source':manifest['bundle_source'],'validation_source':manifest['validation_source']}
(r/'_scratch/reviewkit05-extraction-verification.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
print(json.dumps(record))
