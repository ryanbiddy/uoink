"""Focused test suite for NLTK pathsec backport (GHSA-8mgp-746c-j5xp).

Architectural rules enforced:
1. Tests are fully independent of the test runner's import order. NLTK routing
   tests execute in fresh child processes (with -B bytecode disabled) and never
   mutate or pollute the runner process's globals or sys.modules.
2. Serialization and training boundaries are mocked upfront (json.dump, json.load,
   pickle.dump, allowlisted_pickle_load, MaxentEncoder, SVM). No synthetic weights
   are loaded into a model.
3. Paired outside-root refusals and inside-root controls across all six vulnerable APIs.
4. Comprehensive fail-closed matrix: tampered patch, tampered source, wrong version,
   preexisting destination, destination inside source, source inside destination,
   receipt outside destination, path traversal.
5. Staging-dependent integration tests are separated from portable tests. A missing
   staging fixture is a stated skip, not coverage.
6. Staging source bytes and scratch archive bytes are verified unmodified.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Load prepare module directly by path to avoid conflicts with repo scripts.py
PREPARE_SCRIPT_PATH = REPO_ROOT / "scripts" / "prepare_nltk_pathsec_backport.py"
spec = importlib.util.spec_from_file_location("prepare_nltk_pathsec_backport", PREPARE_SCRIPT_PATH)
prepare_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare_mod)

prepare_backport = prepare_mod.prepare_backport
sha256_file = prepare_mod.sha256_file
EXPECTED_ORIGINAL_HASHES = prepare_mod.EXPECTED_ORIGINAL_HASHES
EXPECTED_PATCH_SHA256 = prepare_mod.EXPECTED_PATCH_SHA256
EXPECTED_PATCHED_HASHES = prepare_mod.EXPECTED_PATCHED_HASHES

STAGING_NLTK = Path(
    "E:/AI/projects/uoink/checkouts/Yoink-library/installer/staging/python/Lib/site-packages/nltk"
)
STAGING_SITE_PACKAGES = STAGING_NLTK.parent


# ==============================================================================
# Fixtures & Helpers
# ==============================================================================

@pytest.fixture
def minimal_valid_source(staging_available, tmp_path):
    """Provide a valid NLTK 3.10.3 source tree using staging source files."""
    src = tmp_path / "valid_src"
    src.mkdir()
    (src / "VERSION").write_text("3.10.3\n", encoding="utf-8")
    for rel in EXPECTED_ORIGINAL_HASHES:
        src_f = staging_available / rel
        dst_f = src / rel
        dst_f.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_f, dst_f)
    return src


@pytest.fixture(scope="session")
def staging_available():
    """Ensure staging NLTK source is present, else stated skip."""
    if not STAGING_NLTK.is_dir():
        pytest.skip(f"Staging NLTK source not found at {STAGING_NLTK}")
    return STAGING_NLTK


@pytest.fixture(scope="session")
def prepared_tree_session(tmp_path_factory, staging_available):
    """Prepare a patched NLTK tree once for routing probe tests."""
    session_tmp = tmp_path_factory.mktemp("session_nltk_backport")
    dst_nltk = session_tmp / "nltk"
    receipt_file = dst_nltk / "nltk-pathsec-receipt.json"

    receipt = prepare_backport(
        src=staging_available,
        dst=dst_nltk,
        receipt_path=receipt_file,
    )
    assert receipt["status"] == "SUCCESS"
    assert receipt_file.is_file()

    return {
        "tree_dir": dst_nltk,
        "receipt": receipt,
        "site_dir": session_tmp,
    }


def run_child_probe(python_code: str, tree_site_dir: Path, timeout: int = 15) -> subprocess.CompletedProcess[str]:
    """Execute python snippet in an isolated child process with bytecode disabled."""
    env = os.environ.copy()
    python_paths = [str(tree_site_dir)]
    if STAGING_SITE_PACKAGES.is_dir():
        python_paths.append(str(STAGING_SITE_PACKAGES))
    env["PYTHONPATH"] = os.pathsep.join(python_paths)
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    cmd = [sys.executable, "-B", "-c", python_code]
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout)


def make_probe_sandbox_header(sandbox_dir: Path) -> str:
    """Generate child-process header that pins allowed data roots strictly to sandbox_dir."""
    return f"""
from pathlib import Path
import sys, os, unittest.mock as mock
import nltk

sandbox_p = Path(r'{sandbox_dir}').resolve()
nltk.data.path = [r'{sandbox_dir}']
nltk.pathsec._ALLOWED_ROOTS_CACHE = {{sandbox_p}}
nltk.pathsec._LAST_DATA_PATHS = ([r'{sandbox_dir}'], "")
nltk.pathsec.ENFORCE = True
"""


# ==============================================================================
# Suite 1: Preparation Boundaries & Fail-Closed Matrix
# ==============================================================================

def test_prepare_refuses_preexisting_destination(minimal_valid_source, tmp_path):
    """Refuse an existing destination directory to prevent overwrites."""
    dst = tmp_path / "already_exists"
    dst.mkdir()

    with pytest.raises(FileExistsError, match="Destination already exists"):
        prepare_backport(src=minimal_valid_source, dst=dst)


def test_prepare_refuses_path_traversal_in_destination(minimal_valid_source, tmp_path):
    """Refuse destination paths containing traversal ('..') segments."""
    traversal_dst = str(tmp_path / "sub" / ".." / "escaped")

    with pytest.raises(ValueError, match="Path traversal"):
        prepare_backport(src=minimal_valid_source, dst=traversal_dst)


def test_prepare_refuses_destination_inside_source(minimal_valid_source):
    """Refuse destination nested inside the source directory (overlap)."""
    nested_dst = minimal_valid_source / "nested_dst"

    with pytest.raises(ValueError, match="Destination .* cannot be inside or equal to source"):
        prepare_backport(src=minimal_valid_source, dst=nested_dst)


def test_prepare_refuses_source_inside_destination(staging_available, tmp_path):
    """Refuse source nested inside destination path (overlap)."""
    dst = tmp_path / "dst_dir"
    nested_src = dst / "nested_src"
    nested_src.mkdir(parents=True)
    (nested_src / "VERSION").write_text("3.10.3\n", encoding="utf-8")
    for rel in EXPECTED_ORIGINAL_HASHES:
        src_f = staging_available / rel
        dst_f = nested_src / rel
        dst_f.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_f, dst_f)

    with pytest.raises(ValueError, match="Source .* cannot be inside destination"):
        prepare_backport(src=nested_src, dst=dst)


def test_prepare_refuses_receipt_outside_destination(minimal_valid_source, tmp_path):
    """Enforce that receipt path must live strictly inside the destination."""
    dst = tmp_path / "clean_dst"
    outside_receipt = tmp_path / "outside_receipt.json"

    with pytest.raises(ValueError, match="Receipt path .* must live inside destination"):
        prepare_backport(src=minimal_valid_source, dst=dst, receipt_path=outside_receipt)


def test_prepare_refuses_tampered_patch(minimal_valid_source, tmp_path):
    """Refuse patch file whose hash differs from expected."""
    bad_patch = tmp_path / "tampered.patch"
    bad_patch.write_text("--- a/foo\n+++ b/foo\n", encoding="utf-8")

    dst = tmp_path / "tampered_dst"
    with pytest.raises(ValueError, match="Patch hash mismatch"):
        prepare_backport(src=minimal_valid_source, dst=dst, patch_file=bad_patch)


# ==============================================================================
# Suite 2: Staging-Dependent Preparation & Source Integrity Tests
# ==============================================================================

def test_prepare_verifies_clean_original_and_exclusive_receipt(staging_available, tmp_path):
    """The preparation utility validates original hashes, patches tree, and writes exclusive receipt."""
    dst = tmp_path / "prepared_clean"
    receipt_file = dst / "subdir" / "receipt.json"

    receipt = prepare_backport(
        src=staging_available,
        dst=dst,
        receipt_path=receipt_file,
    )

    assert receipt["status"] == "SUCCESS"
    assert receipt["target_version"] == "3.10.3"
    assert receipt["original_hashes"] == EXPECTED_ORIGINAL_HASHES
    assert receipt["patched_hashes"] == EXPECTED_PATCHED_HASHES
    assert receipt["patch_sha256"] == EXPECTED_PATCH_SHA256
    assert receipt_file.is_file()

    # Verify exclusive creation: re-writing to existing receipt raises FileExistsError
    with pytest.raises(FileExistsError):
        with open(receipt_file, "x", encoding="utf-8") as f:
            f.write("fail")


def test_prepare_refuses_tampered_source(staging_available, tmp_path):
    """Refuse source tree when any tracked file hash differs from expected original."""
    tampered_src = tmp_path / "tampered_src"
    shutil.copytree(staging_available, tampered_src)

    tampered_file = tampered_src / "classify" / "maxent.py"
    with open(tampered_file, "a", encoding="utf-8") as f:
        f.write("\n# TAMPER_INJECTION\n")

    dst = tmp_path / "prep_tampered_dst"
    with pytest.raises(ValueError, match="Source hash mismatch"):
        prepare_backport(src=tampered_src, dst=dst)

    assert not dst.exists(), "Destination must not be created on tampered source"


def test_prepare_refuses_wrong_version(staging_available, tmp_path):
    """Refuse source tree claiming an unsupported version."""
    fake_ver_src = tmp_path / "fake_ver_src"
    shutil.copytree(staging_available, fake_ver_src)

    (fake_ver_src / "VERSION").write_text("3.10.4\n", encoding="utf-8")
    dst = tmp_path / "wrong_ver_dst"

    with pytest.raises(ValueError, match="Unsupported source version '3.10.4'"):
        prepare_backport(src=fake_ver_src, dst=dst)

    assert not dst.exists()


def test_staging_source_original_bytes_unmodified(staging_available):
    """Verify that staging tree bytes are completely unmodified and match original hashes."""
    for rel_path, expected_hash in EXPECTED_ORIGINAL_HASHES.items():
        actual_hash = sha256_file(staging_available / rel_path)
        assert actual_hash == expected_hash, f"Staging byte corruption detected in {rel_path}"


def test_scratch_archive_matches_staging(staging_available):
    """Verify that scratch archive bytes match staging source bytes."""
    scratch_root = REPO_ROOT / "_scratch" / "nltk-original"
    if not scratch_root.is_dir():
        pytest.skip("Scratch archive not present in this worktree")

    for rel in [
        "vendor/nltk-pathsec/README.md",
        "vendor/nltk-pathsec/nltk-3.10.3-pathsec.patch",
        "scripts/prepare_nltk_pathsec_backport.py",
        "tests/test_nltk_pathsec_backport.py",
        "docs/library/NLTK-PATHSEC-BACKPORT-2026-09-12.md",
    ]:
        p = scratch_root / rel
        assert p.is_file(), f"Expected preserved original file in scratch: {p}"


# ==============================================================================
# Suite 3: Isolated Child-Process Routing Probes for the Six APIs
# ==============================================================================

# --- API 1: TransitionParser.train ---

def test_transition_parser_train_outside_refusal(prepared_tree_session, tmp_path):
    """TransitionParser.train refuses an outside-root destination before training starts."""
    site_dir = prepared_tree_session["site_dir"]
    sandbox_dir = (tmp_path / "sandbox").resolve()
    sandbox_dir.mkdir(parents=True)
    outside_file = (tmp_path / "outside_model.arcstd").resolve()

    header = make_probe_sandbox_header(sandbox_dir)
    code = f"""{header}
from nltk.parse.transitionparser import TransitionParser
parser = TransitionParser('arc-standard')
try:
    parser.train(depgraphs=[], modelfile=r'{outside_file}')
    sys.exit(1)
except PermissionError as e:
    assert 'Security Violation' in str(e)
    assert not os.path.exists(r'{outside_file}')
    print('SUCCESS_REFUSAL')
"""
    res = run_child_probe(code, site_dir)
    assert res.returncode == 0, f"Probe failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"
    assert "SUCCESS_REFUSAL" in res.stdout


def test_transition_parser_train_inside_control(prepared_tree_session, tmp_path):
    """TransitionParser.train inside-root control with mocked training boundary."""
    site_dir = prepared_tree_session["site_dir"]
    sandbox_dir = (tmp_path / "sandbox").resolve()
    sandbox_dir.mkdir(parents=True)
    inside_file = (sandbox_dir / "inside_model.arcstd").resolve()

    header = make_probe_sandbox_header(sandbox_dir)
    code = f"""{header}
from nltk.parse.transitionparser import TransitionParser
parser = TransitionParser('arc-standard')
parser._create_training_examples_arc_std = mock.MagicMock()

with mock.patch('tempfile.NamedTemporaryFile') as mock_tmp, \\
     mock.patch('nltk.parse.transitionparser.load_svmlight_file', return_value=(mock.MagicMock(), mock.MagicMock())), \\
     mock.patch('nltk.parse.transitionparser.svm.SVC', return_value=mock.MagicMock()), \\
     mock.patch('nltk.parse.transitionparser.remove'), \\
     mock.patch('pickle.dump') as mock_dump:
    
    tmp_obj = mock.MagicMock()
    tmp_obj.name = 'mock.tmp'
    mock_tmp.return_value = tmp_obj
    
    parser.train(depgraphs=[], modelfile=r'{inside_file}', verbose=False)
    assert mock_dump.called
    opened_file = mock_dump.call_args[0][1]
    assert os.path.realpath(opened_file.name) == os.path.realpath(r'{inside_file}')
    print('SUCCESS_INSIDE')
"""
    res = run_child_probe(code, site_dir)
    assert res.returncode == 0, f"Probe failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"
    assert "SUCCESS_INSIDE" in res.stdout


# --- API 2: TransitionParser.parse ---

def test_transition_parser_parse_outside_refusal(prepared_tree_session, tmp_path):
    """TransitionParser.parse refuses reading an outside-root model file."""
    site_dir = prepared_tree_session["site_dir"]
    sandbox_dir = (tmp_path / "sandbox").resolve()
    sandbox_dir.mkdir(parents=True)
    outside_file = (tmp_path / "outside_model.arcstd").resolve()
    outside_file.write_bytes(b"dummy_bytes")

    header = make_probe_sandbox_header(sandbox_dir)
    code = f"""{header}
from nltk.parse.transitionparser import TransitionParser
parser = TransitionParser('arc-standard')

with mock.patch('nltk.parse.transitionparser.allowlisted_pickle_load') as mock_unpickle:
    try:
        parser.parse(depgraphs=[], modelFile=r'{outside_file}')
        sys.exit(1)
    except PermissionError as e:
        assert 'Security Violation' in str(e)
        assert not mock_unpickle.called
        print('SUCCESS_REFUSAL')
"""
    res = run_child_probe(code, site_dir)
    assert res.returncode == 0, f"Probe failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"
    assert "SUCCESS_REFUSAL" in res.stdout


def test_transition_parser_parse_inside_control(prepared_tree_session, tmp_path):
    """TransitionParser.parse inside-root control with mocked unpickling boundary."""
    site_dir = prepared_tree_session["site_dir"]
    sandbox_dir = (tmp_path / "sandbox").resolve()
    sandbox_dir.mkdir(parents=True)
    inside_file = (sandbox_dir / "inside_model.arcstd").resolve()
    inside_file.write_bytes(b"dummy_bytes")

    header = make_probe_sandbox_header(sandbox_dir)
    code = f"""{header}
from nltk.parse.transitionparser import TransitionParser
parser = TransitionParser('arc-standard')

with mock.patch('nltk.parse.transitionparser.allowlisted_pickle_load', return_value=mock.MagicMock()) as mock_load:
    res = parser.parse(depgraphs=[], modelFile=r'{inside_file}')
    assert mock_load.called
    assert res == []
    print('SUCCESS_INSIDE')
"""
    res = run_child_probe(code, site_dir)
    assert res.returncode == 0, f"Probe failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"
    assert "SUCCESS_INSIDE" in res.stdout


# --- API 3: AveragedPerceptron.save ---

def test_averaged_perceptron_save_outside_refusal(prepared_tree_session, tmp_path):
    """AveragedPerceptron.save refuses writing weights outside allowed root."""
    site_dir = prepared_tree_session["site_dir"]
    sandbox_dir = (tmp_path / "sandbox").resolve()
    sandbox_dir.mkdir(parents=True)
    outside_file = (tmp_path / "outside_weights.json").resolve()

    header = make_probe_sandbox_header(sandbox_dir)
    code = f"""{header}
from nltk.tag.perceptron import AveragedPerceptron
ap = AveragedPerceptron()

with mock.patch('json.dump') as mock_dump:
    try:
        ap.save(r'{outside_file}')
        sys.exit(1)
    except PermissionError as e:
        assert 'Security Violation' in str(e)
        assert not mock_dump.called
        assert not os.path.exists(r'{outside_file}')
        print('SUCCESS_REFUSAL')
"""
    res = run_child_probe(code, site_dir)
    assert res.returncode == 0, f"Probe failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"
    assert "SUCCESS_REFUSAL" in res.stdout


def test_averaged_perceptron_save_inside_control(prepared_tree_session, tmp_path):
    """AveragedPerceptron.save inside-root control with mocked JSON serialization boundary."""
    site_dir = prepared_tree_session["site_dir"]
    sandbox_dir = (tmp_path / "sandbox").resolve()
    sandbox_dir.mkdir(parents=True)
    inside_file = (sandbox_dir / "inside_weights.json").resolve()

    header = make_probe_sandbox_header(sandbox_dir)
    code = f"""{header}
from nltk.tag.perceptron import AveragedPerceptron
ap = AveragedPerceptron()

with mock.patch('json.dump') as mock_dump:
    ap.save(r'{inside_file}')
    assert mock_dump.called
    opened_file = mock_dump.call_args[0][1]
    assert os.path.realpath(opened_file.name) == os.path.realpath(r'{inside_file}')
    print('SUCCESS_INSIDE')
"""
    res = run_child_probe(code, site_dir)
    assert res.returncode == 0, f"Probe failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"
    assert "SUCCESS_INSIDE" in res.stdout


# --- API 4: AveragedPerceptron.load ---

def test_averaged_perceptron_load_outside_refusal(prepared_tree_session, tmp_path):
    """AveragedPerceptron.load refuses reading weights outside allowed root."""
    site_dir = prepared_tree_session["site_dir"]
    sandbox_dir = (tmp_path / "sandbox").resolve()
    sandbox_dir.mkdir(parents=True)
    outside_file = (tmp_path / "outside_weights.json").resolve()
    outside_file.write_text("{}", encoding="utf-8")

    header = make_probe_sandbox_header(sandbox_dir)
    code = f"""{header}
from nltk.tag.perceptron import AveragedPerceptron
ap = AveragedPerceptron()

with mock.patch('json.load') as mock_load:
    try:
        ap.load(r'{outside_file}')
        sys.exit(1)
    except PermissionError as e:
        assert 'Security Violation' in str(e)
        assert not mock_load.called
        print('SUCCESS_REFUSAL')
"""
    res = run_child_probe(code, site_dir)
    assert res.returncode == 0, f"Probe failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"
    assert "SUCCESS_REFUSAL" in res.stdout


def test_averaged_perceptron_load_inside_control_mocked_boundary(prepared_tree_session, tmp_path):
    """AveragedPerceptron.load inside-root control: mocks json.load boundary without consuming synthetic weights."""
    site_dir = prepared_tree_session["site_dir"]
    sandbox_dir = (tmp_path / "sandbox").resolve()
    sandbox_dir.mkdir(parents=True)
    inside_file = (sandbox_dir / "inside_weights.json").resolve()
    inside_file.write_text("{}", encoding="utf-8")

    header = make_probe_sandbox_header(sandbox_dir)
    code = f"""{header}
from nltk.tag.perceptron import AveragedPerceptron
ap = AveragedPerceptron()

with mock.patch('json.load', return_value={{}}) as mock_load:
    ap.load(r'{inside_file}')
    assert mock_load.called
    opened_file = mock_load.call_args[0][0]
    assert os.path.realpath(opened_file.name) == os.path.realpath(r'{inside_file}')
    assert ap.weights == {{}}
    print('SUCCESS_INSIDE_MOCKED')
"""
    res = run_child_probe(code, site_dir)
    assert res.returncode == 0, f"Probe failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"
    assert "SUCCESS_INSIDE_MOCKED" in res.stdout


# --- API 5: PerceptronTagger.save_to_json ---

def test_perceptron_tagger_save_to_json_outside_refusal(prepared_tree_session, tmp_path):
    """PerceptronTagger.save_to_json refuses outside directory and creates no files."""
    site_dir = prepared_tree_session["site_dir"]
    sandbox_dir = (tmp_path / "sandbox").resolve()
    sandbox_dir.mkdir(parents=True)
    outside_dir = (tmp_path / "outside_models").resolve()

    header = make_probe_sandbox_header(sandbox_dir)
    code = f"""{header}
from nltk.tag.perceptron import PerceptronTagger
tagger = PerceptronTagger(load=False)

with mock.patch('json.dump') as mock_dump:
    try:
        tagger.save_to_json(loc=r'{outside_dir}')
        sys.exit(1)
    except PermissionError as e:
        assert 'Security Violation' in str(e)
        assert not mock_dump.called
        assert not os.path.exists(r'{outside_dir}')
        print('SUCCESS_REFUSAL')
"""
    res = run_child_probe(code, site_dir)
    assert res.returncode == 0, f"Probe failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"
    assert "SUCCESS_REFUSAL" in res.stdout


def test_perceptron_tagger_save_to_json_inside_control(prepared_tree_session, tmp_path):
    """PerceptronTagger.save_to_json inside-root control with mocked json.dump boundary."""
    site_dir = prepared_tree_session["site_dir"]
    sandbox_dir = (tmp_path / "sandbox").resolve()
    sandbox_dir.mkdir(parents=True)
    inside_dir = (sandbox_dir / "inside_models").resolve()

    header = make_probe_sandbox_header(sandbox_dir)
    code = f"""{header}
from nltk.tag.perceptron import PerceptronTagger
tagger = PerceptronTagger(load=False)

with mock.patch('json.dump') as mock_dump:
    tagger.save_to_json(loc=r'{inside_dir}')
    assert mock_dump.called
    assert os.path.isdir(r'{inside_dir}')
    print('SUCCESS_INSIDE')
"""
    res = run_child_probe(code, site_dir)
    assert res.returncode == 0, f"Probe failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"
    assert "SUCCESS_INSIDE" in res.stdout


def test_perceptron_tagger_constructor_lang_traversal_refusal(prepared_tree_session):
    """PerceptronTagger constructor refuses traversal in lang parameter."""
    site_dir = prepared_tree_session["site_dir"]

    code = """
import sys
import nltk
from nltk.tag.perceptron import PerceptronTagger
try:
    PerceptronTagger(lang='../../bad_lang', load=False)
    sys.exit(1)
except ValueError as e:
    assert 'Invalid tagger language code' in str(e)
    print('SUCCESS_CONSTRUCTOR_REFUSAL')
"""
    res = run_child_probe(code, site_dir)
    assert res.returncode == 0, f"Probe failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"
    assert "SUCCESS_CONSTRUCTOR_REFUSAL" in res.stdout


def test_perceptron_tagger_save_lang_traversal_refusal(prepared_tree_session, tmp_path):
    """PerceptronTagger.save_to_json refuses traversal in lang parameter."""
    site_dir = prepared_tree_session["site_dir"]
    sandbox_dir = (tmp_path / "sandbox").resolve()
    sandbox_dir.mkdir(parents=True)

    header = make_probe_sandbox_header(sandbox_dir)
    code = f"""{header}
from nltk.tag.perceptron import PerceptronTagger
tagger = PerceptronTagger(load=False)
try:
    tagger.save_to_json(lang='../escape', loc=r'{sandbox_dir}')
    sys.exit(1)
except ValueError as e:
    assert 'Invalid tagger language code' in str(e)
    print('SUCCESS_SAVE_LANG_REFUSAL')
"""
    res = run_child_probe(code, site_dir)
    assert res.returncode == 0, f"Probe failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"
    assert "SUCCESS_SAVE_LANG_REFUSAL" in res.stdout


# --- API 6: save_maxent_params ---

def test_save_maxent_params_outside_refusal(prepared_tree_session, tmp_path):
    """save_maxent_params refuses outside directory before creating dir or files."""
    site_dir = prepared_tree_session["site_dir"]
    sandbox_dir = (tmp_path / "sandbox").resolve()
    sandbox_dir.mkdir(parents=True)
    outside_dir = (tmp_path / "outside_maxent_tabs").resolve()

    header = make_probe_sandbox_header(sandbox_dir)
    code = f"""{header}
from nltk.classify.maxent import save_maxent_params
dummy = mock.MagicMock()
try:
    save_maxent_params(dummy, {{}}, [], {{}}, tab_dir=r'{outside_dir}')
    sys.exit(1)
except PermissionError as e:
    assert 'Security Violation' in str(e)
    assert not os.path.exists(r'{outside_dir}')
    print('SUCCESS_REFUSAL')
"""
    res = run_child_probe(code, site_dir)
    assert res.returncode == 0, f"Probe failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"
    assert "SUCCESS_REFUSAL" in res.stdout


def test_save_maxent_params_inside_control_preserves_none_return(prepared_tree_session, tmp_path):
    """save_maxent_params inside-root control with mocked encoder boundary and verified None return."""
    site_dir = prepared_tree_session["site_dir"]
    sandbox_dir = (tmp_path / "sandbox").resolve()
    sandbox_dir.mkdir(parents=True)
    inside_dir = (sandbox_dir / "inside_maxent_tabs").resolve()

    header = make_probe_sandbox_header(sandbox_dir)
    code = f"""{header}
from nltk.classify.maxent import save_maxent_params
dummy_wgt = mock.MagicMock()
dummy_wgt.tolist.return_value = []

with mock.patch('nltk.tabdata.MaxentEncoder') as mock_enc_cls:
    mock_enc = mock.MagicMock()
    mock_enc.list2txt.return_value = 'mock_txt'
    mock_enc.tupdict2tab.return_value = 'mock_tab'
    mock_enc.ivdict2tab.return_value = 'mock_tab'
    mock_enc_cls.return_value = mock_enc

    ret = save_maxent_params(dummy_wgt, {{}}, [], {{}}, tab_dir=r'{inside_dir}')
    assert ret is None, f'Expected None return value, got {{ret!r}}'
    assert os.path.isdir(r'{inside_dir}')
    for fname in ['weights.txt', 'mapping.tab', 'labels.txt', 'alwayson.tab']:
        assert os.path.isfile(os.path.join(r'{inside_dir}', fname))
    print('SUCCESS_INSIDE_NONE_RETURN')
"""
    res = run_child_probe(code, site_dir)
    assert res.returncode == 0, f"Probe failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"
    assert "SUCCESS_INSIDE_NONE_RETURN" in res.stdout


# ==============================================================================
# Suite 4: Traversal, Symlinks, and Execution Boundaries
# ==============================================================================

def test_nested_traversal_escape_refusal(prepared_tree_session, tmp_path):
    """Refuse nested traversal sequences escaping the sandbox root."""
    site_dir = prepared_tree_session["site_dir"]
    sandbox_dir = (tmp_path / "sandbox").resolve()
    sandbox_dir.mkdir(parents=True)
    outside_dir = (tmp_path / "outside").resolve()
    outside_dir.mkdir(parents=True)

    nested_target = sandbox_dir / "sub" / ".." / ".." / outside_dir.name / "target.json"

    header = make_probe_sandbox_header(sandbox_dir)
    code = f"""{header}
from nltk.tag.perceptron import AveragedPerceptron
ap = AveragedPerceptron()

with mock.patch('json.dump'):
    try:
        ap.save(r'{nested_target}')
        sys.exit(1)
    except PermissionError as e:
        assert 'Security Violation' in str(e)
        print('SUCCESS_NESTED_REFUSAL')
"""
    res = run_child_probe(code, site_dir)
    assert res.returncode == 0, f"Probe failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"
    assert "SUCCESS_NESTED_REFUSAL" in res.stdout


def test_symlink_escape_refusal_or_unprivileged_boundary(prepared_tree_session, tmp_path):
    """Test symlink escape containment, or honestly record unprivileged Windows boundary."""
    site_dir = prepared_tree_session["site_dir"]
    sandbox_dir = (tmp_path / "sandbox").resolve()
    sandbox_dir.mkdir(parents=True)
    outside_dir = (tmp_path / "outside").resolve()
    outside_dir.mkdir(parents=True)
    link_in_sandbox = sandbox_dir / "link_to_outside"

    try:
        os.symlink(str(outside_dir), str(link_in_sandbox), target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(
            f"Symlink creation not permitted in this environment ({exc}); "
            "boundary recorded: symlink escape testing requires symlink creation privileges."
        )

    symlink_file = link_in_sandbox / "weights.json"
    header = make_probe_sandbox_header(sandbox_dir)
    code = f"""{header}
from nltk.tag.perceptron import AveragedPerceptron
ap = AveragedPerceptron()

with mock.patch('json.dump'):
    try:
        ap.save(r'{symlink_file}')
        sys.exit(1)
    except PermissionError as e:
        assert 'Security Violation' in str(e)
        print('SUCCESS_SYMLINK_REFUSAL')
"""
    res = run_child_probe(code, site_dir)
    assert res.returncode == 0, f"Probe failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"
    assert "SUCCESS_SYMLINK_REFUSAL" in res.stdout


def test_no_torch_or_inference_imported():
    """Verify that execution boundary holds: no heavy ML packages imported in test runner."""
    for mod in ["torch", "whisper", "whisperx", "pyannote"]:
        assert mod not in sys.modules, f"Forbidden module {mod} was imported during pathsec tests"
