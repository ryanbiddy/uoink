"""Copy exact committed source text and record selected-body identities."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
out = Path(__file__).absolute().parent
root = out.parents[1]
source = root / 'docs/library/proof/runtime-security-scope-2026-09-13/candidate03-source'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
manifest_raw = (source / 'ORIGINAL-CANDIDATE03-SOURCE-SHA256.json').read_bytes()
rows = {row['file']: row for row in json.loads(manifest_raw)['payloads']}
inputs = {
    'base.py.txt': ('upstream/huggingface--transformers/src/transformers/pipelines/base.py', '853e42ad66b34aed2b8b523450c822632d3f162f82a1d9e46f003d6963e98bf2'),
    'pt_utils.py.txt': ('upstream/huggingface--transformers/src/transformers/pipelines/pt_utils.py', '0ed35580ed6e7759f46d833025c94cbe7209aada0db3d69e75c5ee0af24bfd23'),
    'asr.py.txt': ('retained/installer/staging/python/Lib/site-packages/whisperx/asr.py', 'f25d2dfd0cfcbcb6cd2850ba213bf715f92d4369401274e534557448876da565'),
}
selection = {
    'base.py.txt': {'Pipeline': ['__init__', 'device_placement', '_ensure_tensor_on_device', 'get_inference_context', 'forward', '__call__', 'run_single'], None: ['_reform_generator']},
    'pt_utils.py.txt': {'PipelineIterator': None},
    'asr.py.txt': {'FasterWhisperPipeline': ['__init__', '_sanitize_parameters', 'preprocess', '_forward', 'postprocess', 'get_iterator']},
}
bindings, selected = [], []
(out / 'inputs').mkdir(exist_ok=False)
for name, (relative, expected) in inputs.items():
    raw = (source / relative).read_bytes()
    assert len(raw) == rows[relative]['bytes'] and sha(raw) == rows[relative]['sha256'] == expected
    (out / 'inputs' / name).write_bytes(raw)
    bindings.append({'file': name, 'source': str(source / relative), 'bytes': len(raw), 'sha256': expected})
    tree = ast.parse(raw)
    for cls, methods in selection[name].items():
        candidates = tree.body if cls is None else next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls).body
        for node in candidates:
            if isinstance(node, ast.FunctionDef) and (methods is None or node.name in methods):
                selected.append({'file': name, 'class': cls, 'method': node.name, 'line': node.lineno, 'end_line': node.end_lineno,
                    'body_ast_sha256': sha(ast.dump(ast.Module(body=node.body, type_ignores=[]), include_attributes=False).encode()),
                    'execute': not (cls == 'Pipeline' and node.name == '__init__')})
(out / 'inputs/ORIGINAL-SOURCE-MANIFEST.json').write_bytes(manifest_raw)
for name in ['REVIEW.md', 'commit-bindings.json']:
    raw = (source / name).read_bytes()
    assert sha(raw) == rows[name]['sha256']
    (out / 'inputs' / name).write_bytes(raw)
(out / 'SOURCE-BINDINGS.json').write_text(json.dumps({'created_utc': datetime.now(timezone.utc).isoformat(), 'bindings': bindings,
    'selected_bodies': selected, 'selection': selection, 'source_manifest_sha256': sha(manifest_raw), 'source_executed': False}, indent=2)+'\n', encoding='utf-8', newline='\n')
print(json.dumps({'sources': len(bindings), 'selected_methods': len(selected), 'source_executed': False}))
