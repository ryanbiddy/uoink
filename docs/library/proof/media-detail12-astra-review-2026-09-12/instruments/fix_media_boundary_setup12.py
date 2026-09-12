import difflib,hashlib,json
from pathlib import Path
r=Path(__file__).resolve().parents[1]
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\2dae80cc-01a\gemini')
p=w/'tests/test_media_detail_boundaries.py'
old=p.read_bytes();text=old.decode('utf8')
needle="'video_id':'saved-media','title':'Synthetic item'"
assert text.count(needle)==1
new=text.replace(needle,"'video_id':'saved-media','slug':'saved-media','title':'Synthetic item'")
out=r/'_scratch/media-detail12-review'
(out/'boundary-missing-slug-original.txt').write_bytes(old)
(out/'boundary-setup.diff').write_text(''.join(difflib.unified_diff(text.splitlines(True),new.splitlines(True),fromfile='missing-required-slug',tofile='supplied-required-slug')),encoding='utf8')
p.write_text(new,encoding='utf8',newline='\n')
(out/'boundary-setup-diagnosis.json').write_text(json.dumps({'attempt':'astra-media12-boundary-negative02','result':'4 assertion failures, 6 setup errors','reason':'New integrator fixture omitted the schema-required slug; six backend bodies did not execute. Supply only that required field; behavior assertions remain byte-identical.','old_sha256':hashlib.sha256(old).hexdigest(),'new_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'next':'astra-media12-boundary-negative03 on unchanged worker product'},indent=2)+'\n',encoding='utf8')
print('Preserved failed new-test setup; supplied required slug only.')
