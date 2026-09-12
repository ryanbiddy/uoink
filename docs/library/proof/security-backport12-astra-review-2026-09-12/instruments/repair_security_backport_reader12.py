import difflib,json
from pathlib import Path
s=Path(__file__).resolve().parent
old=(s/'review_security_backport12.py').read_text(encoding='utf8')
diagnosis={'result':'reader failed before metadata verification','error':"KeyError: files",'reason':'This worker seal is a direct path-to-hash object, not the integrator files wrapper.','repair':'Iterate the actual top-level mapping; retain every hash and size check. Use a fresh review02 directory. No product observation rerun.'}
(s/'security-backport12-review/reader-failure.json').write_text(json.dumps(diagnosis,indent=2)+'\n',encoding='utf8',newline='\n')
new=old.replace("out=s/'security-backport12-review'","out=s/'security-backport12-review02'").replace("manifest['files']","manifest")
target=s/'review_security_backport12_02.py';assert not target.exists();target.write_text(new,encoding='utf8',newline='\n')
(s/'review_security_backport12_02.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='review_security_backport12.py',tofile=target.name)),encoding='utf8',newline='\n')
