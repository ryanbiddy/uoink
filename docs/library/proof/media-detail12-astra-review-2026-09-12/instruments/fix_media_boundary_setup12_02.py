import difflib,hashlib,json
from pathlib import Path
r=Path(__file__).resolve().parents[1]
p=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\2dae80cc-01a\gemini\tests\test_media_detail_boundaries.py')
old=p.read_bytes();text=old.decode('utf8')
needle="'slug':'saved-media','title':'Synthetic item'"
assert text.count(needle)==1
new=text.replace(needle,"'slug':'saved-media','yoinked_at':'2026-09-12T00:00:00Z','title':'Synthetic item'")
out=r/'_scratch/media-detail12-review'
(out/'boundary-missing-date-original.txt').write_bytes(old)
(out/'boundary-setup02.diff').write_text(''.join(difflib.unified_diff(text.splitlines(True),new.splitlines(True),fromfile='missing-required-date',tofile='supplied-required-date')),encoding='utf8')
p.write_text(new,encoding='utf8',newline='\n')
(out/'boundary-setup02-diagnosis.json').write_text(json.dumps({'attempt':'astra-media12-boundary-negative03','result':'4 assertion failures, 6 setup errors','reason':'The same new fixture also omitted required yoinked_at. Supply this schema field only. No assertion changed and no existing accepted test edited.','old_sha256':hashlib.sha256(old).hexdigest(),'new_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'next':'astra-media12-boundary-negative04 on unchanged worker product'},indent=2)+'\n',encoding='utf8')
print('Preserved second setup result; supplied required capture date.')
