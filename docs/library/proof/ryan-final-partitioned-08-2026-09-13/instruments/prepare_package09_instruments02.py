"""Prepare fresh observers only; no build, test, application or model starts."""
import ast, collections, difflib, hashlib, json, shutil
from pathlib import Path

r = Path(__file__).resolve().parents[1]
s = r / '_scratch'
source = 'e53fe0e52131d7b210484b7c89850d1bcb31b9ee'
rows = []

def adapt(name, target, transform, scope):
    before = (s / name).read_text(encoding='utf8')
    after = transform(before)
    assert before != after
    dest = s / target
    assert not dest.exists() or dest.read_text(encoding='utf8')==after, dest
    if dest.suffix == '.py': ast.parse(after)
    dest.write_text(after, encoding='utf8', newline='\n')
    (s / (target + '.diff')).write_text(''.join(difflib.unified_diff(
        before.splitlines(True), after.splitlines(True), fromfile=name, tofile=target)),
        encoding='utf8', newline='\n')
    rows.append({'before': name, 'after': target, 'scope': scope,
                 'before_sha256': hashlib.sha256((s / name).read_bytes()).hexdigest(),
                 'after_sha256': hashlib.sha256(dest.read_bytes()).hexdigest(),
                 'executed': False})

def base(text):
    return (text.replace('package08', 'package09').replace('package-08', 'package-09')
            .replace('2026-09-12', '2026-09-13').replace('September 12', 'September 13')
            .replace('b8e44fbc0a16950a22b29ead66951fcb80b2d6e8', source))

for name in ('review_package08_notices.py', 'verify_package08_graph.py', 'review_package08_pins.py'):
    adapt(name, name.replace('08', '09'), base, 'Fresh package/date/source labels only; original observation checks unchanged.')

def wheel(text):
    text = base(text)
    needle = "'29b23c360f22f414dc7336bb39178cc7bcbf6021ed2733cde173f09dba19abb3')]"
    assert text.count(needle) == 1
    text = text.replace(needle, "'29b23c360f22f414dc7336bb39178cc7bcbf6021ed2733cde173f09dba19abb3'),\n"
                        "    ('vendor/nltk-pathsec/dist/nltk-3.10.3+uoink.pathsec1-py3-none-any.whl', '969f623541344ade83ea267130e016d6cb8a223ecaaf28fb3d7a663c7e3c60d8')]")
    text = text.replace("wheel = r / '_scratch' / name", "wheel = r / name if name.startswith('vendor/') else r / '_scratch' / name")
    return text.replace('separately verified PyPI repair wheels', 'separately verified upstream repair wheels and the reviewed local NLTK wheel')
adapt('compare_package08_repair_wheels.py', 'compare_package09_repair_wheels.py', wheel,
      'Add fixed-hash local NLTK artifact to existing per-member comparisons; only pip-rewritten RECORD excluded, no assertion removed.')

def finalizer(text):
    text = base(text)
    assert "'nltk':'3.10.3'" in text
    text = text.replace("'nltk':'3.10.3'", "'nltk':'3.10.3+uoink.pathsec1'")
    text = text.replace("'prepare_package09_instruments.py','finalize_package09.py.diff'", "'prepare_package09_instruments.py','finalize_package09.py.diff'")
    return text
adapt('finalize_package08.py', 'finalize_package09.py', finalizer,
      'Fresh labels and reviewed local NLTK version expectation. This is a packaging observer, not a frozen acceptance fixture.')

def tree(text):
    text = (text.replace('ryan-final-partitioned-06-2026-09-12', 'ryan-final-partitioned-07-2026-09-13')
            .replace('seal_partitioned_final_tree06.py', 'seal_partitioned_final_tree07.py')
            .replace('_scratch/ryan-final-partitioned-05/expected-membership.json', '_scratch/ryan-final-partitioned-06/expected-membership.json'))
    needle = "allowed = ('tests/test_dashboard_media_detail_truth.py::','tests/test_media_detail_boundaries.py::')\nassert not missing and len(added)==23 and all(n.startswith(allowed) for n in added)"
    assert needle in text
    before = set(json.loads((s/'ryan-final-partitioned-06/expected-membership.json').read_text()))
    current = set(json.loads((s/'ryan-final-partitioned-07/expected-membership.json').read_text()))
    grouped = collections.Counter(x.split('::')[0] for x in current-before)
    assert not before-current and len(current-before)==147
    accepted = {'tests/test_installer_signing.py', 'tests/test_signing_host_selection.py', 'tests/test_signing_receipts.py',
                'tests/test_nltk_pathsec_backport.py', 'tests/test_nltk_preparation_boundaries.py', 'tests/test_runtime_graph.py', 'tests/test_runtime_graph_boundaries.py',
                'tests/test_nltk_local_wheel.py', 'tests/test_nltk_wheel_boundaries.py'}
    assert set(grouped).issubset(accepted), grouped
    replacement = 'expected_added_by_file = '+repr(dict(sorted(grouped.items())))+'\n'
    replacement += "actual_added_by_file = {name:sum(n.split('::')[0]==name for n in added) for name in expected_added_by_file}\n"
    replacement += "assert not missing and len(added)==147 and actual_added_by_file==expected_added_by_file and all(n.split('::')[0] in expected_added_by_file for n in added)"
    text = text.replace(needle, replacement)
    text = text.replace("'seal_partitioned_final_tree07.py'):", "'seal_partitioned_final_tree07.py','run_combined_candidate13.py','prepare_package09_instruments.py','prepare_package09_instruments02.py','package09-preparation-refusal01.json','seal_partitioned_final_tree07.py.diff'):")
    return text.replace('added regression file only', 'only added regression files; exact new case membership checked')
adapt('seal_partitioned_final_tree06.py', 'seal_partitioned_final_tree07.py', tree,
      'Fresh seal label; compare actual 147 new cases by file against prior 2,582-case observation; retain failures and unchanged-test check.')

def build(text):
    needle = "Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue"
    assert text.count(needle)==1
    return text.replace(needle, "Get-ChildItem Env: | Where-Object { $_.Name -match '(API_KEY|AUTH_TOKEN|ACCESS_TOKEN|BASE_URL|OAUTH_TOKEN)' -or $_.Name -match '^(ANTHROPIC_|OPENAI_|GEMINI_|GOOGLE_API_|XAI_|GROK_|CLAUDE_CODE_USE_)' } | ForEach-Object { [Environment]::SetEnvironmentVariable($_.Name,$null,'Process') }\n$env:HF_HUB_OFFLINE = '1'\n$env:TRANSFORMERS_OFFLINE = '1'")
adapt('build_library_candidate.ps1', 'build_library_candidate09.ps1', build,
      'Retain exact-source/branch and recursive-target safeguards; scrub all inherited provider overrides and forbid model-network fallback. No Clean.')

archive = s / 'package08-preserved-before09'
archive.mkdir(exist_ok=False)
old = r / 'build/Uoink-Setup-3.8.0.exe'
def sha(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()
expected = '69a5394d842dc7fb5ac770d65954894231b03533bc99db922f34793f372fd06c'
assert old.stat().st_size==389570940 and sha(old)==expected
target = archive / old.name
shutil.copyfile(old,target)
assert sha(old)==sha(target)==expected
preserved = [{'source':str(old), 'archive':str(target), 'sha256':expected, 'bytes':target.stat().st_size}]
# Only the known current-receipt name is eligible; no recursive build search.
receipt = r / 'build/Uoink-Setup-3.8.0.exe.signature.json'
if receipt.is_file():
    dst=archive/receipt.name;shutil.copyfile(receipt,dst)
    assert sha(receipt)==sha(dst)
    preserved.append({'source':str(receipt),'archive':str(dst),'sha256':sha(dst),'bytes':dst.stat().st_size})
(archive/'receipt.json').write_text(json.dumps({'files':preserved,'verified':True,'build_started':False},indent=2)+'\n',encoding='utf8')
(s/'package09-instrument-adaptations.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({'adapted':len(rows),'old_exe_preserved':True,'source':source,'build_started':False}))
