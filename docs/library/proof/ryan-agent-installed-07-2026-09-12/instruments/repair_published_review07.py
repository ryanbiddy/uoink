from pathlib import Path
import ast,difflib,json
r=Path(__file__).resolve().parents[1];oldpath=r/'_scratch/review_published07.py'
old=oldpath.read_text();needle="(profile/'records/stdio').glob('*/events.jsonl')"
assert old.count(needle)==1
new=old.replace(needle,"(profile/'records').glob('stdio-*/events.jsonl')",1)
ast.parse(new)
path=r/'_scratch/review_published07_02.py'
with path.open('x',encoding='utf8',newline='\n') as f:f.write(new)
with path.with_suffix('.py.diff').open('x',encoding='utf8',newline='\n') as f:
    f.write(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile=oldpath.name,tofile=path.name)))
with (r/'_scratch/published07-review-failure01.json').open('x',encoding='utf8',newline='\n') as f:
    f.write(json.dumps({'exit_code':1,'stage':'independent evidence review, not product observation',
        'retained_tool_diagnostic':'review_published07.py line 25: assert len(records)==1; AssertionError: []',
        'source':'Tool-returned diagnostic, retained as structured transcription',
        'diagnosis':'Tap uses records/stdio-39880, not records/stdio/*',
        'product_observations_rerun':False},indent=2)+'\n')
