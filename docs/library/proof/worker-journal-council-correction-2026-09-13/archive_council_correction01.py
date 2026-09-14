"""Archive fixed documentary files; no payload execution or model access."""
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'docs/library/proof/worker-journal-council-correction-2026-09-13'
OBS = '_scratch/council-correction-observation01/'
NAMES = ('ACTUAL-APPLY.json','ACTUAL-COMPLETION.json','ACTUAL-DISPATCH.json','ACTUAL-EXPORT.json',
         'ACTUAL-REPORT-READ.json','ACTUAL-VIEW-CHECK.json','ACTUAL-WORKER-PATCH.json','agent.json',
         'DISPATCH-PREPARATION-NOTE.md','events.json','ROOT-INPUT-CHECK.json','ROOT-VIEW-METADATA-CHECK.json',
         'run.json','tool-metadata.json','view-metadata.json','WORKER-REPORT.md','worker.patch')
FILES = [(OBS+name, name) for name in NAMES] + [
 ('_scratch/export_council_correction01.py','export_council_correction01.py'),
 ('_scratch/archive_council_correction01.py','archive_council_correction01.py'),
 ('docs/library/ASTRA-WORKER-JOURNAL-CORRECTION-VERDICT-2026-09-13.md','ROOT-VERDICT.md'),
 ('docs/library/ASTRA-WORKER-JOURNAL-SOURCE-ADDENDUM-2026-09-13.md','ASTRA-SOURCE-ADDENDUM.md'),
 ('_scratch/worker-journal-council-correction-source-review01/TEXT-AND-RECEIPT-CHECKS.json','PEER-TEXT-AND-RECEIPT-CHECKS.json'),
]
def sha(raw): return hashlib.sha256(raw).hexdigest()
def checked(path):
    assert path.resolve().is_relative_to(ROOT)
    for part in (path, *path.parents):
        assert not part.is_symlink() and not part.is_junction()
        if part == ROOT: break
    raw=path.read_bytes()
    assert len(raw) <= 1048576
    return raw
assert not DEST.exists()
payloads=[(src, dst, checked(ROOT/src)) for src,dst in FILES]
assert len({dst for _,dst,_ in payloads})==len(payloads)
DEST.mkdir()
copyrows=[]
for src,dst,raw in payloads:
    (DEST/dst).write_bytes(raw)
    assert checked(ROOT/src)==checked(DEST/dst)==raw
    copyrows.append({'source':src,'path':dst,'bytes':len(raw),'sha256':sha(raw)})
(DEST/'FIXED-COPY-LIST.json').write_text(json.dumps(copyrows,indent=2)+'\n',encoding='utf-8')
(DEST/'.gitattributes').write_bytes(b'* -text\n')
rows=[{'path':p.name,'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in sorted(DEST.iterdir())]
(DEST/'SHA256.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'payloads':len(rows),'bytes':sum(row['bytes'] for row in rows),'seal_sha256':sha((DEST/'SHA256.json').read_bytes())}))
