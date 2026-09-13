"""Negative controls for evidence parsing; no network or package execution."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('graph_boundary_checker', ROOT / 'scripts/check_runtime_graph.py')
graph = importlib.util.module_from_spec(spec)
spec.loader.exec_module(graph)


def seal(root):
    mapping = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in root.rglob('*') if p.is_file() and p.name != 'SHA256.json'}
    (root / 'SHA256.json').write_text(json.dumps(mapping), encoding='utf8')


def fixture(root, requirement=''):
    (root / 'pypi').mkdir()
    (root / 'metadata').mkdir()
    data = {'info': {'name': 'demo', 'version': '1.0.0'}, 'releases': {'1.0.0': [{
        'filename': 'demo-1.0.0-py3-none-any.whl', 'packagetype': 'bdist_wheel',
        'url': 'https://example.test/demo.whl', 'size': 100, 'digests': {'sha256': 'a'*64}}]}}
    (root / 'pypi/demo.json').write_text(json.dumps(data), encoding='utf8')
    metadata = root / 'metadata/demo-1.0.0-py3-none-any.whl.metadata'
    metadata.write_text('Metadata-Version: 2.1\nName: demo\nVersion: 1.0.0\n'+requirement, encoding='utf8')
    seal(root)
    return metadata


def test_lock_root_extra_changes_required_edges(tmp_path):
    fixture(tmp_path, 'Requires-Dist: child; extra == "feature"\n')
    selection = tmp_path / 'selection.txt'
    selection.write_text('demo[feature]==1.0.0\n', encoding='utf8')
    base = graph.check_runtime_graph({'demo': '1.0.0'}, tmp_path)
    with_extra = graph.check_runtime_graph(graph.parse_selection(selection), tmp_path)
    assert base['passed'] is True
    assert with_extra['passed'] is False
    assert any(row['target'] == 'child' for row in with_extra['missing_packages'])


def test_duplicate_selection_key_is_rejected(tmp_path):
    path = tmp_path / 'selection.json'
    path.write_text('{"demo":"1.0.0","demo":"2.0.0"}', encoding='utf8')
    with pytest.raises(ValueError, match='Duplicate'):
        graph.parse_selection(path)


def test_duplicate_manifest_stops_dependent_reading(tmp_path, monkeypatch):
    fixture(tmp_path)
    digest = hashlib.sha256((tmp_path / 'pypi/demo.json').read_bytes()).hexdigest()
    (tmp_path / 'SHA256.json').write_text('{"pypi/demo.json":"'+digest+'","pypi/demo.json":"'+digest+'"}', encoding='utf8')
    def forbidden(*args, **kwargs):
        pytest.fail('Dependent evidence was read after integrity failure')
    monkeypatch.setattr(graph, 'find_pypi_json_for_package', forbidden)
    result = graph.check_runtime_graph({'demo': '1.0.0'}, tmp_path)
    assert result['passed'] is False and result['manifest_errors']


@pytest.mark.parametrize('url', ['https://', 'http://example.test/x.whl', 'https://user:secret@example.test/x.whl',
                                     'https://example.test/x.whl#fragment', 'https://exam\nple.test/x.whl'])
def test_invalid_artifact_urls_do_not_qualify(tmp_path, url):
    fixture(tmp_path)
    path = tmp_path / 'pypi/demo.json'
    data = json.loads(path.read_text(encoding='utf8'))
    data['releases']['1.0.0'][0]['url'] = url
    path.write_text(json.dumps(data), encoding='utf8')
    seal(tmp_path)
    result = graph.check_runtime_graph({'demo': '1.0.0'}, tmp_path)
    assert result['passed'] is False and result['wheel_failures']


def test_unbound_dist_info_metadata_is_not_exact_wheel_evidence(tmp_path):
    metadata = fixture(tmp_path)
    data = metadata.read_bytes()
    metadata.unlink()
    fallback = tmp_path / 'metadata/demo-1.0.0.dist-info/METADATA'
    fallback.parent.mkdir()
    fallback.write_bytes(data)
    seal(tmp_path)
    result = graph.check_runtime_graph({'demo': '1.0.0'}, tmp_path)
    assert result['passed'] is False and result['incomplete_evidence']


def test_metadata_change_after_manifest_check_is_not_consumed(tmp_path, monkeypatch):
    metadata = fixture(tmp_path, 'Requires-Dist: missing-child\n')
    verify = graph.verify_evidence_integrity
    def change_after_hash(root):
        result = verify(root)
        metadata.write_text('Metadata-Version: 2.1\nName: demo\nVersion: 1.0.0\n', encoding='utf8')
        return result
    monkeypatch.setattr(graph, 'verify_evidence_integrity', change_after_hash)
    result = graph.check_runtime_graph({'demo': '1.0.0'}, tmp_path)
    assert result['passed'] is False and result['incomplete_evidence']


def test_duplicate_singleton_metadata_is_rejected(tmp_path):
    metadata = fixture(tmp_path)
    with metadata.open('a', encoding='utf8') as stream:
        stream.write('Name: other\n')
    seal(tmp_path)
    result = graph.check_runtime_graph({'demo': '1.0.0'}, tmp_path)
    assert result['passed'] is False and result['incomplete_evidence']


def test_integrity_bypass_stops_before_any_dependent_read(tmp_path, monkeypatch):
    fixture(tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail('Integrity bypass still consumed evidence')
    monkeypatch.setattr(graph, 'find_pypi_json_for_package', forbidden)
    result = graph.check_runtime_graph({'demo': '1.0.0'}, tmp_path, verify_manifest=False)
    assert result['passed'] is False


@pytest.mark.parametrize('root', [r'C:relative', r'C:\proof:stream', r'C:\NUL\proof',
                                  r'\\?\C:\proof', r'\\server\share\proof'])
def test_unsafe_root_rejected_before_filesystem_probe(root, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Unsafe root reached a filesystem probe')
    monkeypatch.setattr(Path, 'lstat', forbidden)
    ok, errors, _ = graph.verify_evidence_integrity(Path(root))
    assert ok is False and errors


def test_target_override_cannot_mix_markers_and_wheel_tags(tmp_path):
    fixture(tmp_path)
    environment = dict(graph.TARGET_ENV, sys_platform='linux')
    result = graph.check_runtime_graph({'demo': '1.0.0'}, tmp_path, target_env=environment)
    assert result['passed'] is False and result['selection_errors']
