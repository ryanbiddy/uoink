"""Portable negative controls for the fixed NLTK preparation operation."""
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('nltk_boundary_prepare', ROOT / 'scripts/prepare_nltk_pathsec_backport.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


@pytest.fixture
def source(tmp_path):
    directory = tmp_path / 'source'
    directory.mkdir()
    (directory / 'VERSION').write_text('3.10.3\n', encoding='utf8')
    for name in prepare.EXPECTED_ORIGINAL_HASHES:
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / 'vendor/nltk-pathsec/original' / name, path)
    return directory


def test_tampered_patch_refused_before_destination_creation(source, tmp_path):
    patch = tmp_path / 'tampered.patch'
    patch.write_text('arbitrary bytes\n', encoding='utf8')
    destination = tmp_path / 'destination'
    with pytest.raises(ValueError, match='Patch hash mismatch'):
        prepare.prepare_backport(source, destination, patch_file=patch)
    assert not destination.exists()


def test_no_expected_hash_override(source, tmp_path):
    destination = tmp_path / 'destination'
    patch = tmp_path / 'empty-unreviewed.patch'
    patch.write_text('Unreviewed patch with no changed files\n', encoding='utf8')
    with pytest.raises(TypeError):
        prepare.prepare_backport(source, destination, patch_file=patch,
                                 expected_patch_hash=prepare.sha256_file(patch))
    assert not destination.exists()


@pytest.mark.parametrize('receipt', ['C:receipt.json', 'safe.json:stream', 'NUL.json', '\\\\?\\C:\\receipt.json', '../outside.json'])
def test_windows_receipt_aliases_refused_before_copy(source, tmp_path, receipt):
    destination = tmp_path / 'destination'
    with pytest.raises((ValueError, PermissionError)):
        prepare.prepare_backport(source, destination, receipt_path=receipt)
    assert not destination.exists()


def test_receipt_cannot_replace_copied_file(source, tmp_path):
    (source / 'existing.json').write_text('original\n', encoding='utf8')
    destination = tmp_path / 'destination'
    with pytest.raises(ValueError, match='replace a source entry'):
        prepare.prepare_backport(source, destination, receipt_path='existing.json')
    assert not destination.exists()
    assert (source / 'existing.json').read_text(encoding='utf8') == 'original\n'


def test_complete_copy_hashes_and_receipt_are_bound(source, tmp_path):
    (source / 'extra.txt').write_bytes(b'unchanged non-patched source')
    before = prepare.tree_hashes(source)
    destination = tmp_path / 'destination'
    record = prepare.prepare_backport(source, destination, receipt_path='receipts/result.json')
    assert record['source_tree_hashes'] == before
    assert record['prepared_tree_hashes']['extra.txt'] == before['extra.txt']
    assert record['patched_hashes'] == prepare.EXPECTED_PATCHED_HASHES
    assert prepare.tree_hashes(source) == before
    assert record['release_ready'] is False
    saved = json.loads((destination / 'receipts/result.json').read_text(encoding='utf8'))
    assert saved == record


def test_ancestor_link_is_refused_before_leaf_probe(tmp_path, monkeypatch):
    linked = tmp_path / 'linked'
    leaf = linked / 'unread' / 'file'
    inspected = []
    def check(path):
        inspected.append(path)
        return path == linked
    monkeypatch.setattr(prepare, 'is_symlink_or_reparse', check)
    with pytest.raises(PermissionError):
        prepare.verify_no_links_or_reparse(leaf, 'Synthetic linked ancestor')
    assert linked in inspected and leaf not in inspected
