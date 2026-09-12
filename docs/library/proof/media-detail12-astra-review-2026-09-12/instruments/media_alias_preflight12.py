from pathlib import Path
r=Path(__file__).resolve().parents[1]
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\2dae80cc-01a\gemini')
out=r/'_scratch/media-detail12-review'
(out/'timestamp-alias-repair-brief.md').write_text('''# Preserve stored time aliases

Final diff review found that the new transcript and diarization projection omit
start_seconds/end_seconds although the renderer reads those stored fields.
Add one new regression covering all three segment containers, retain its
original-source failure, and include those aliases in the two missing allowlists.
Do not generate times or change existing assertions. Rerun the 58-case union in
the worker, apply the small raw delta with three-way apply, and rerun in checkout.
The 57-pass observations remain accurate for their earlier source.
''',encoding='utf8')
p=w/'tests/test_media_detail_boundaries.py'
text=p.read_text(encoding='utf8')
assert 'def test_saved_time_aliases_are_preserved' not in text
text+='''

def test_saved_time_aliases_are_preserved(item):
    path,register,request=item
    cue={'start_seconds':34,'end_seconds':46,'text':'SYNTHETIC stored cue'}
    path.write_text(json.dumps({'transcript':[cue],'segments':[cue],'diarization':{'segments':[cue]}}),encoding='utf8')
    code,data=request()
    assert code==200
    details=data['details']
    for rows in (details['transcript'],details['segments'],details['diarization']['segments']):
        assert rows[0]['start_seconds']==34 and rows[0]['end_seconds']==46
'''
p.write_text(text,encoding='utf8',newline='\n')
