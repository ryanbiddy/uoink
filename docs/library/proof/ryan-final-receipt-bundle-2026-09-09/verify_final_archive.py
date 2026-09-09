"""Verify the final ZIP and its exact relationship to the completed operator preflight."""
import argparse,hashlib,json,zipfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--zip',type=Path,required=True);p.add_argument('--label',required=True);a=p.parse_args()
r=Path(__file__).resolve().parents[1]
assert a.label.replace('-','').isalnum()
out=r/'_scratch'/a.label;out.mkdir(exist_ok=False)
folder=out/'Uoink Receipt Kit';folder.mkdir()
def sha(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
with zipfile.ZipFile(a.zip) as archive:
 for name in archive.namelist():assert (folder/name).resolve().is_relative_to(folder.resolve()),name
 archive.extractall(folder)
manifest=json.loads((folder/'BUNDLE-SHA256.json').read_text(encoding='utf8'))
for name,row in manifest['files'].items():
 file=folder/name
 assert file.resolve().is_relative_to(folder.resolve()),name
 assert file.stat().st_size==row['bytes'] and sha(file)==row['sha256'],name
assert {q.relative_to(folder).as_posix() for q in folder.rglob('*') if q.is_file()}==set(manifest['files'])|{'BUNDLE-SHA256.json'}
preflight=r/'_scratch/portable-operator-01'
original=preflight/'Uoink Receipt Kit'
observation=json.loads((preflight/'observation.json').read_text(encoding='utf8'))
assert len(observation['results'])==2 and all(x['exit']==0 for x in observation['results'])
assert len(observation['profile_names'])==9 and observation['app_created'] is False
old=json.loads((original/'BUNDLE-SHA256.json').read_text(encoding='utf8'))
assert old['validation_source']==manifest['validation_source']
same=[];metadata=[]
for name,row in old['files'].items():
 if name in ('package-manifest.json','c22-operator-manifest.json'):
  before=json.loads((original/name).read_text(encoding='utf8'))
  after=json.loads((folder/name).read_text(encoding='utf8'))
  assert before.pop('bundle_source')==old['bundle_source']
  assert after.pop('bundle_source')==manifest['bundle_source']
  assert before==after,name
  metadata.append(name)
 else:
  assert manifest['files'][name]==row,name
  same.append(name)
result={'scope':'Final ZIP extraction/hash check and binding to the completed first operator preparation; no repeated product/scenario measurement',
 'zip':str(a.zip.resolve()),'zip_sha256':sha(a.zip),'bundle_source':manifest['bundle_source'],
 'validation_source':manifest['validation_source'],'payload_files_verified':len(manifest['files']),
 'all_extracted_file_hashes_verified':True,'preflight_source':observation['validation_source'],
 'byte_identical_preflight_inputs':same,'provenance_metadata_only_change':metadata,
 'preflight_commands_passed':True,'preflight_profile_count':len(observation['profile_names']),
 'setup_executed':False,'client_executed':False,'installed_credit':False}
(out/'observation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in result.items() if k!='byte_identical_preflight_inputs'},indent=2))
