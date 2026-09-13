"""Static path-semantics check for Gemini finding 2; no product/model imports."""
import hashlib,json,sys
from pathlib import Path,PureWindowsPath
root=Path(__file__).resolve().parents[1]
out=root/'_scratch/asset-council-windows-case01'
out.mkdir(exist_ok=False)
target=out/'CaseProbe.txt'
target.write_bytes(b'synthetic path identity probe; not an asset')
literal=Path(str(target).lower()).absolute()
resolved=literal.resolve(strict=True)
record={
    'platform':sys.platform,'python':sys.version,
    'scope':'Windows path equality only; no 8.3 alias, model, download or production execution',
    'pure_drive_case_equal':PureWindowsPath('e:/Example/Snapshot')==PureWindowsPath('E:/Example/Snapshot'),
    'pure_component_case_equal':PureWindowsPath('E:/Example/Snapshot')==PureWindowsPath('E:/example/snapshot'),
    'absolute_path':str(literal),'resolved_path':str(resolved),
    'string_spelling_differs':str(literal)!=str(resolved),
    'absolute_path_equal_resolved':literal==resolved,
    'source_sha256':hashlib.sha256((root/'whisper_runner.py').read_bytes()).hexdigest(),
    'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
}
(out/'result.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
assert sys.platform=='win32' and record['pure_drive_case_equal'] and record['pure_component_case_equal']
assert record['string_spelling_differs'] and record['absolute_path_equal_resolved']
print(json.dumps(record))
