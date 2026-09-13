"""Read-only pytest observation: record membership and actual reports, never alter tests."""
import json,os
from pathlib import Path
import pytest
from _pytest.subtests import SubtestReport

DEST=Path(os.environ['IG_PARTITION_RECEIPT_PATH']).resolve()
ROOT=Path(__file__).resolve().parents[1]
assert DEST.is_relative_to(ROOT/'_scratch') and not DEST.exists()
DEST.mkdir(parents=True)
REPORTS=[]
NEXT_INDEX=0
SUBTEST_ORDINALS={}

def _save(name,value):
    (DEST/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf8')

def pytest_collection_finish(session):
    _save('membership.json',[item.nodeid for item in session.items])

@pytest.hookimpl(hookwrapper=True,tryfirst=True)
def pytest_runtest_logreport(report):
    global NEXT_INDEX
    row={'nodeid':report.nodeid,'when':report.when,'outcome':report.outcome,
         'duration':report.duration,'wasxfail':getattr(report,'wasxfail',None),
         'report_index':NEXT_INDEX,'report_type':type(report).__name__,
         'report_class':type(report).__module__+'.'+type(report).__name__,
         'outcome_before_hooks':report.outcome,'subtest':None}
    NEXT_INDEX+=1
    if isinstance(report,SubtestReport):
        ordinal=SUBTEST_ORDINALS.get(report.nodeid,0)+1
        SUBTEST_ORDINALS[report.nodeid]=ordinal
        row['subtest']={'ordinal':ordinal,'context':report.context._to_json()}
    yield
    row['outcome']=report.outcome
    row['outcome_transition_reason']=(str(report.longrepr)
        if row['outcome_before_hooks']!=report.outcome else None)
    REPORTS.append(row)
    with (DEST/'reports.jsonl').open('a',encoding='utf8') as stream:
        stream.write(json.dumps(row,ensure_ascii=False)+'\n')

def pytest_sessionfinish(session,exitstatus):
    _save('session.json',{'exit':int(exitstatus),'tests_collected':session.testscollected,
                          'tests_failed':session.testsfailed,'reports':len(REPORTS)})
