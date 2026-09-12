import difflib,json
from pathlib import Path
r=Path(__file__).resolve().parents[1]
p=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\2dae80cc-01a\gemini\tests\test_media_detail_boundaries.py')
old=p.read_bytes();text=old.decode('utf8');needle="'sidecar_path':str(p),'source_type'"
assert text.count(needle)==1
new=text.replace(needle,"'sidecar_path':str(p),'corpus_path':str(root/'media.md'),'source_type'")
out=r/'_scratch/media-detail12-review'
(out/'boundary-missing-corpus-original.txt').write_bytes(old)
(out/'boundary-setup03.diff').write_text(''.join(difflib.unified_diff(text.splitlines(True),new.splitlines(True),fromfile='missing-required-corpus',tofile='supplied-required-corpus')),encoding='utf8')
p.write_text(new,encoding='utf8',newline='\n')
(out/'boundary-setup03-diagnosis.json').write_text(json.dumps({'attempt':'astra-media12-boundary-negative04','result':'4 assertion failures, 6 setup errors','reason':'Schema migrations/0001_initial_schema.sql additionally requires corpus_path. Supply this final missing NOT NULL field. Existing assertions and accepted tests unchanged.','next':'astra-media12-boundary-negative05 on unchanged worker product'},indent=2)+'\n',encoding='utf8')
print('Preserved third setup result; supplied required corpus path after schema review.')
