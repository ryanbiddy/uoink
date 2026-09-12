import ast,json,shutil,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1]
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\d8840cdd-c3a\gemini')
p=r/'_scratch/native-note12-review';p.mkdir(exist_ok=False)
raw=(w/'tests/test_native_note_display_regressions.py').read_text(encoding='utf8')
shutil.copyfile(w/'tests/test_native_note_display_regressions.py',p/'rejected-worker-tests.py.txt')
shutil.copyfile(w/'docs/library/NATIVE-NOTE-DISPLAY-WORKER-2026-09-12.md',p/'worker-report-original.md.txt')
subprocess.run(['git','add','-N','--','tests/test_native_note_display_regressions.py','docs/library/NATIVE-NOTE-DISPLAY-WORKER-2026-09-12.md'],cwd=w,check=True)
(p/'worker-original.patch').write_bytes(subprocess.check_output(['git','diff','--binary'],cwd=w))
harness=next(ast.literal_eval(n.value) for n in ast.parse(raw).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='DASHBOARD_NODE_HARNESS' for t in n.targets))
prefix='''"""Real note capture and renderer states, including false-success regressions."""
import json
from pathlib import Path
import subprocess
import pytest
import index as index_mod
import notes
import server

ROOT=Path(__file__).resolve().parents[1]
# DOM adapter derived from the rejected worker module; production JS executes unchanged.
'''
body='''
def render(action, **values):
    result=subprocess.run(['node','-e',HARNESS], input=json.dumps(dict(action=action,**values)), cwd=ROOT, text=True, capture_output=True, timeout=15)
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)

NOTE={'video_id':'note_review','source_type':'note','platform':'note','title':'Saved idea','author':'You'}

@pytest.mark.parametrize('payload',[{'synthetic_fixture':True},{'note':True},{'text':True},{'note':'  \\n\\t'},{'markdown':[]},{'transcript':[{'start':0}]}])
def test_metadata_is_not_note_content(payload):
    health=server.compute_health(dict(source_type='note',platform='note',**payload))
    assert health['transcript']=='missing'
    assert 'Needs attention' in render('healthException',health=health)['result']

def test_real_note_capture_enrichment_and_card(tmp_path):
    idx=index_mod.Index.open(tmp_path/'isolated.db')
    try:
        built=notes.build_note(text='The saved word is AMBER.',title='Saved idea')
        vid=notes.persist_note(idx,built,data_root=tmp_path/'output')
        row=idx.get_yoink(vid)
        assert 'The saved word is AMBER.' in Path(row['corpus_path']).read_text(encoding='utf8')
        sidecar=json.loads(Path(row['sidecar_path']).read_text(encoding='utf8'))
        fresh=server.compute_health(sidecar)
        assert fresh['transcript']=='ok'
        assert all(fresh[k]=='skipped' for k in ('screenshots','comments','hook','comment_intelligence'))
        assert json.loads(row['health_score_json'])==fresh==sidecar['health']
        enriched=server._enrich_yoink_rows(idx,[row])[0]
        assert enriched['health']==fresh
        card=render('cardHtml',row=enriched)['result']
        assert 'Needs attention' not in card
        assert 'source-type-chip">note<' in card
    finally:
        idx.close()

def test_note_missing_text_stays_unhealthy():
    health=server.compute_health({'source_type':'note','note':''})
    assert health['transcript']=='missing'
    assert health['screenshots']==health['comments']=='skipped'
    assert 'Needs attention' in render('cardHtml',row=dict(NOTE,health=health))['result']

@pytest.mark.parametrize('status,text,expected',[('loading','','checking'),('ready','AMBER','ready'),('empty','','empty'),('no_markdown','','unavailable'),('unavailable','','unavailable')])
def test_note_readiness_tracks_text_result(status,text,expected):
    result=render('renderYoinkDetail',row=NOTE,markdown=text,markdownState=status)
    assert result['factMeta']==expected
    facts=render('yoinkFactsHtml',row=NOTE,markdown=text,markdownState=status)['result']
    assert 'Saved details' in facts
    if expected!='ready':
        assert '>ready<' not in facts
    assert 'needs re-capture' not in facts

def test_note_has_no_media_controls_or_placeholders():
    result=render('renderYoinkDetail',row=NOTE,markdown='AMBER',markdownState='ready')
    assert 'Saved note <em>source.</em>' in result['heading']
    assert 'screenshot-grid' not in result['detail']
    assert 'Video screenshots appear here' not in result['detail']
    assert result['retranscribeDisabled'] is True
    facts=render('yoinkFactsHtml',row=NOTE,markdown='AMBER')['result']
    assert 'Note file' in facts
    for title in ('Duration','Speakers','Transcript checker','Re-transcription'):
        assert title not in facts

def test_source_labels():
    cases=[('note','note','note'),('note','x','note'),('image','image','image'),('page','web','page'),('x_article','x','article'),('x_thread','x','post'),('reddit_thread','reddit','thread'),('video','youtube','video'),('episode','podcast','podcast')]
    for st,platform,label in cases:
        assert render('mediaLabelFor',row={'source_type':st,'platform':platform})['result']==label
    assert render('mediaLabelFor',row={'platform':'youtube','is_live':True})['result']=='live stream'

def test_video_health_and_fields_remain_applicable():
    health=server.compute_health({'source_type':'video','transcript':None,'screenshots':[],'comments':[]})
    assert health['transcript']==health['screenshots']==health['comments']=='missing'
    facts=render('yoinkFactsHtml',row={'source_type':'video','platform':'youtube'})['result']
    for title in ('Duration','Speakers','Transcript checker','Re-transcription'):
        assert title in facts
'''
source=prefix+'HARNESS='+repr(harness)+'\n'+body
for root in (r,w):
    target=root/'tests/test_note_readiness_truth.py';assert not target.exists();target.write_text(source,encoding='utf8',newline='\n')
print('Original worker patch preserved; new independent regressions written to both roots.')
