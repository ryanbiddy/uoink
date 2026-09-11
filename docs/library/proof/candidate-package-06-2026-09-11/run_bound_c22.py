"""Run the original portable C22 CLI against an explicitly selected package seal."""
import argparse,hashlib,json,sys
from pathlib import Path
assert sys.flags.isolated and sys.flags.no_site
p=argparse.ArgumentParser()
p.add_argument('--kit-root',required=True,type=Path)
p.add_argument('--package-seal',required=True,type=Path)
p.add_argument('--entry',choices=['cli','browser'],default='cli')
a,remaining=p.parse_known_args()
kit=a.kit_root.resolve(strict=True);seal=a.package_seal.resolve(strict=True)
assert kit.name=='install_receipt' and (kit/'__init__.py').is_file()
payload=json.loads((seal/'SHA256.json').read_text(encoding='utf8'))['files']
assert isinstance(payload,dict)
for name,row in payload.items():
 q=(seal/name).resolve(strict=True);assert q.is_relative_to(seal)
 with q.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
 assert q.stat().st_size==row['bytes'] and digest==row['sha256'],name
sys.path.insert(0,str(kit.parent))
from install_receipt import manifest
assert Path(manifest.__file__).resolve()==kit/'manifest.py'
manifest.CANDIDATE_PACKAGE_02_DIR=seal
manifest.load_candidate_package_02()
if a.entry=='cli':
 from install_receipt.cli import main
else:
 from install_receipt.browser_checkpoint import main
raise SystemExit(main(remaining))
