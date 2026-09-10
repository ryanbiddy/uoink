"""Read-only pytest observation: record membership and actual reports, never alter tests."""
import json,os
from pathlib import Path

DEST=Path(os.environ['IG_PARTITION_RECEIPT_PATH']).resolve()
ROOT=Path(__file__).resolve().parents[1]
assert DEST.is_relative_to(ROOT/'_scratch') and not DEST.exists()
DEST.mkdir(parents=True)
REPORTS=[]

def _save(name,value):
    (DEST/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf8')

def pytest_collection_finish(session):
    _save('membership.json',[item.nodeid for item in session.items])

def pytest_runtest_logreport(report):
    row={'nodeid':report.nodeid,'when':report.when,'outcome':report.outcome,
         'duration':report.duration,'wasxfail':getattr(report,'wasxfail',None)}
    REPORTS.append(row)
    with (DEST/'reports.jsonl').open('a',encoding='utf8') as stream:
        stream.write(json.dumps(row,ensure_ascii=False)+'\n')

def pytest_sessionfinish(session,exitstatus):
    _save('session.json',{'exit':int(exitstatus),'tests_collected':session.testscollected,
                          'tests_failed':session.testsfailed,'reports':len(REPORTS)})
