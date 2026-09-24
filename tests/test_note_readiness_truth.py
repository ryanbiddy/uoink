"""Real note capture and renderer states, including false-success regressions."""
import json
from pathlib import Path
import subprocess
import pytest
import index as index_mod
import notes
import server

ROOT=Path(__file__).resolve().parents[1]
# DOM adapter derived from the rejected worker module; production JS executes unchanged.
HARNESS='\nconst fs = require(\'node:fs\');\nconst vm = require(\'node:vm\');\n\nconst page = fs.readFileSync(\'assets/dashboard/index.html\', \'utf8\');\nconst scriptStart = page.indexOf(\'<script>\') + 8;\nconst initCall = page.indexOf(\'    init().catch(\');\nconst scriptCode = page.slice(scriptStart, initCall > 0 ? initCall : undefined);\n\nfunction createContext(initialState = {}, initialEls = {}) {\n  const elements = {};\n  const getEl = (id) => {\n    if (!elements[id]) {\n      elements[id] = {\n        id,\n        disabled: false,\n        textContent: \'\',\n        innerHTML: \'\',\n        title: \'\',\n        dataset: {},\n        classList: {\n          add: () => {},\n          remove: () => {},\n          contains: () => false,\n          toggle: () => {},\n        },\n        setAttribute: () => {},\n        getAttribute: () => null,\n        querySelectorAll: () => [],\n      };\n    }\n    return elements[id];\n  };\n\n  const fakeDocument = {\n    getElementById: (id) => getEl(id),\n    querySelector: (sel) => null,\n    querySelectorAll: (sel) => [],\n  };\n\n  const ctx = {\n    document: fakeDocument,\n    window: { addEventListener: () => {} },\n    navigator: { clipboard: { writeText: () => Promise.resolve() } },\n    console,\n    fetch: () => Promise.reject(new Error("network forbidden")),\n    setTimeout: () => {},\n    clearTimeout: () => {},\n    URL: { createObjectURL: () => "blob:mock", revokeObjectURL: () => {} },\n  };\n  vm.createContext(ctx);\n  // Execute the dashboard script in the context and bind state and els to globalThis\n  vm.runInContext(scriptCode + \'\\n;globalThis.state = state; globalThis.els = els;\', ctx);\n  return ctx;\n}\n\nconst input = JSON.parse(fs.readFileSync(0, \'utf8\'));\nconst action = input.action;\nconst ctx = createContext();\n\nif (action === "mediaLabelFor") {\n  const result = ctx.mediaLabelFor(input.row, input.sidecar || {});\n  process.stdout.write(JSON.stringify({ result }));\n} else if (action === "healthException") {\n  const result = ctx.healthException(input.health);\n  process.stdout.write(JSON.stringify({ result }));\n} else if (action === "cardHtml") {\n  const result = ctx.cardHtml(input.row);\n  process.stdout.write(JSON.stringify({ result }));\n} else if (action === "yoinkFactsHtml") {\n  ctx.state.selectedYoinkMarkdown = input.markdown || "";\n  ctx.state.selectedYoinkMarkdownState = input.markdownState || "ready";\n  ctx.state.selectedYoinkSidecar = input.sidecar || null;\n  ctx.state.selectedYoinkSidecarError = input.sidecarError || "";\n  const result = ctx.yoinkFactsHtml(input.row, input.sidecar || {});\n  process.stdout.write(JSON.stringify({ result }));\n} else if (action === "renderYoinkDetail") {\n  ctx.state.selectedYoink = input.row;\n  ctx.state.selectedYoinkSidecar = input.sidecar || null;\n  ctx.state.selectedYoinkMarkdown = input.markdown || "";\n  ctx.state.selectedYoinkMarkdownState = input.markdownState || "ready";\n  ctx.renderYoinkDetail();\n  const heading = ctx.els.yoinkHeading.innerHTML;\n  const subhead = ctx.els.yoinkSubhead.textContent;\n  const factMeta = ctx.els.yoinkFactMeta.textContent;\n  const detail = ctx.els.yoinkDetail.innerHTML;\n  const retranscribeDisabled = ctx.els.yoinkRetranscribe.disabled;\n  const retranscribeTitle = ctx.els.yoinkRetranscribe.title;\n  process.stdout.write(JSON.stringify({\n    heading, subhead, factMeta, detail, retranscribeDisabled, retranscribeTitle\n  }));\n} else {\n  throw new Error("Unknown action: " + action);\n}\n'

def render(action, **values):
    result=subprocess.run(['node','-e',HARNESS], input=json.dumps(dict(action=action,**values)), cwd=ROOT, text=True, capture_output=True, timeout=15)
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)

NOTE={'video_id':'note_review','source_type':'note','platform':'note','title':'Saved idea','author':'You'}

@pytest.mark.parametrize('payload',[{'synthetic_fixture':True},{'note':True},{'text':True},{'note':'  \n\t'},{'markdown':[]},{'transcript':[{'start':0}]}])
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
