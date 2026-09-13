"""Focused test suite for NLTK pathsec backport (GHSA-8mgp-746c-j5xp).

Covers:
1. Deterministic preparation utility:
   - Verification of unchanged original NLTK 3.10.3 staging source hashes.
   - Refusal on tampered input source (hash mismatch).
   - Refusal on unsupported version (VERSION != 3.10.3).
   - Refusal on preexisting destination (reapplied input refusal).
   - Refusal on path traversal in destination (..).
2. The six vulnerable APIs paired with outside-root refusals and inside-root controls:
   - TransitionParser.train (outside refusal vs inside routing; training intercepted)
   - TransitionParser.parse (outside refusal vs inside routing; unpickling intercepted)
   - AveragedPerceptron.save (outside refusal vs inside routing)
   - AveragedPerceptron.load (outside refusal vs inside routing)
   - PerceptronTagger.save_to_json (outside refusal vs inside routing)
   - save_maxent_params (outside refusal vs inside routing)
3. Nested path traversal and symlink escapes (where platform permits).
4. Strict enforcement of execution boundaries:
   - No checkpoints loaded, no models unpickled, no training or inference executed.
   - Honest identification of un-testable platform boundaries (e.g. unprivileged Windows symlinks).
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure repo root is on sys.path for test utilities
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Direct module import for prepare script to avoid shadowing by repo scripts.py
PREPARE_SCRIPT_PATH = REPO_ROOT / "scripts" / "prepare_nltk_pathsec_backport.py"
spec = importlib.util.spec_from_file_location("prepare_nltk_pathsec_backport", PREPARE_SCRIPT_PATH)
prepare_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare_mod)

prepare_backport = prepare_mod.prepare_backport
EXPECTED_ORIGINAL_HASHES = prepare_mod.EXPECTED_ORIGINAL_HASHES
sha256_file = prepare_mod.sha256_file

STAGING_NLTK = Path(
    "E:/AI/projects/uoink/checkouts/Yoink-library/installer/staging/python/Lib/site-packages/nltk"
)
STAGING_SITE_PACKAGES = STAGING_NLTK.parent
if STAGING_SITE_PACKAGES.is_dir() and str(STAGING_SITE_PACKAGES) not in sys.path:
    # Append so that dependencies like defusedxml are found without shadowing patched nltk
    sys.path.append(str(STAGING_SITE_PACKAGES))


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture(scope="session")
def staging_available():
    """Ensure staging NLTK source is present."""
    if not STAGING_NLTK.is_dir():
        pytest.skip(f"Staging NLTK source not found at {STAGING_NLTK}")
    return STAGING_NLTK


@pytest.fixture(scope="session")
def prepared_tree_session(tmp_path_factory, staging_available):
    """Prepare a patched NLTK tree once for the test session."""
    session_tmp = tmp_path_factory.mktemp("session_nltk_backport")
    dst_nltk = session_tmp / "nltk"
    receipt_path = session_tmp / "receipt.json"

    receipt = prepare_backport(
        src=staging_available,
        dst=dst_nltk,
        receipt_path=receipt_path,
    )
    assert receipt["status"] == "SUCCESS"

    # Put session_tmp at the front of sys.path so 'import nltk' resolves to the patched tree
    if str(session_tmp) not in sys.path:
        sys.path.insert(0, str(session_tmp))

    # Purge any previously loaded nltk modules
    for k in list(sys.modules.keys()):
        if k == "nltk" or k.startswith("nltk."):
            del sys.modules[k]

    import nltk
    import nltk.pathsec as pathsec
    from nltk.classify.maxent import save_maxent_params
    from nltk.parse.transitionparser import TransitionParser
    from nltk.tag.perceptron import AveragedPerceptron, PerceptronTagger

    pathsec.ENFORCE = True

    return {
        "nltk": nltk,
        "pathsec": pathsec,
        "TransitionParser": TransitionParser,
        "AveragedPerceptron": AveragedPerceptron,
        "PerceptronTagger": PerceptronTagger,
        "save_maxent_params": save_maxent_params,
        "tree_dir": dst_nltk,
        "receipt": receipt,
    }


@pytest.fixture
def sandbox_env(tmp_path, prepared_tree_session):
    """Provide an allowed sandbox directory and an outside target directory for each test."""
    pathsec = prepared_tree_session["pathsec"]
    nltk = prepared_tree_session["nltk"]

    sandbox_dir = (tmp_path / "sandbox").resolve()
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    outside_dir = (tmp_path / "outside_target").resolve()
    outside_dir.mkdir(parents=True, exist_ok=True)

    # Restrict allowed data roots to strictly the sandbox_dir
    nltk.data.path = [str(sandbox_dir)]
    # Clear pathsec caches so only sandbox_dir is authorized
    pathsec._ALLOWED_ROOTS_CACHE = {sandbox_dir}
    pathsec._LAST_DATA_PATHS = ([str(sandbox_dir)], "")
    pathsec.ENFORCE = True

    return {
        "sandbox_dir": sandbox_dir,
        "outside_dir": outside_dir,
        "pathsec": pathsec,
        "nltk": nltk,
        "TransitionParser": prepared_tree_session["TransitionParser"],
        "AveragedPerceptron": prepared_tree_session["AveragedPerceptron"],
        "PerceptronTagger": prepared_tree_session["PerceptronTagger"],
        "save_maxent_params": prepared_tree_session["save_maxent_params"],
    }


# ==============================================================================
# Suite 1: Preparation Utility Integrity & Fail-Closed Matrix
# ==============================================================================

def test_prepare_verifies_clean_original_and_leaves_staging_intact(staging_available, tmp_path):
    """The preparation utility verifies original hashes and never modifies staging."""
    before_hashes = {
        rel: sha256_file(staging_available / rel) for rel in EXPECTED_ORIGINAL_HASHES
    }
    assert before_hashes == EXPECTED_ORIGINAL_HASHES

    dst = tmp_path / "prep_clean"
    receipt = prepare_backport(src=staging_available, dst=dst)

    assert receipt["status"] == "SUCCESS"
    assert receipt["target_version"] == "3.10.3"
    assert receipt["original_hashes"] == EXPECTED_ORIGINAL_HASHES

    # Check that staging is completely untouched
    after_hashes = {
        rel: sha256_file(staging_available / rel) for rel in EXPECTED_ORIGINAL_HASHES
    }
    assert after_hashes == before_hashes


def test_prepare_refuses_tampered_input(staging_available, tmp_path):
    """The preparation utility refuses an input source tree with tampered hashes."""
    tampered_src = tmp_path / "tampered_nltk"
    shutil.copytree(staging_available, tampered_src)

    target_file = tampered_src / "classify" / "maxent.py"
    with open(target_file, "a", encoding="utf-8") as f:
        f.write("\n# TAMPERED\n")

    dst = tmp_path / "prep_from_tampered"
    with pytest.raises(ValueError, match="Source hash mismatch"):
        prepare_backport(src=tampered_src, dst=dst)

    assert not dst.exists(), "Destination should not be created when source is tampered"


def test_prepare_refuses_wrong_version(staging_available, tmp_path):
    """The preparation utility refuses a source tree claiming an unexpected version."""
    fake_ver_src = tmp_path / "fake_ver_nltk"
    shutil.copytree(staging_available, fake_ver_src)

    version_file = fake_ver_src / "VERSION"
    with open(version_file, "w", encoding="utf-8") as vf:
        vf.write("3.10.4\n")

    dst = tmp_path / "prep_wrong_ver"
    with pytest.raises(ValueError, match="Unsupported source version '3.10.4'"):
        prepare_backport(src=fake_ver_src, dst=dst)

    assert not dst.exists()


def test_prepare_refuses_preexisting_destination(staging_available, tmp_path):
    """The preparation utility refuses to overwrite an existing destination."""
    existing_dst = tmp_path / "already_exists"
    existing_dst.mkdir(parents=True, exist_ok=True)

    with pytest.raises(FileExistsError, match="Destination already exists"):
        prepare_backport(src=staging_available, dst=existing_dst)


def test_prepare_refuses_path_traversal_in_destination(staging_available, tmp_path):
    """The preparation utility refuses destination paths with traversal components."""
    traversal_dst = str(tmp_path / "sub" / ".." / "escaped")

    with pytest.raises(ValueError, match="Path traversal detected"):
        prepare_backport(src=staging_available, dst=traversal_dst)


# ==============================================================================
# Suite 2: The Six Vulnerable APIs - Paired Refusal & Inside Controls
# ==============================================================================

# --- API 1: TransitionParser.train ---

def test_transition_parser_train_outside_refusal(sandbox_env):
    """TransitionParser.train must refuse an outside-root destination before training starts."""
    TransitionParser = sandbox_env["TransitionParser"]
    outside_file = sandbox_env["outside_dir"] / "model.arcstd"

    parser = TransitionParser("arc-standard")
    # Training must fail-fast without executing dataset generation or SVM training
    with pytest.raises(PermissionError, match="Security Violation"):
        parser.train(depgraphs=[], modelfile=str(outside_file))

    assert not outside_file.exists(), "No file should be written outside the root"


def test_transition_parser_train_inside_control(sandbox_env):
    """TransitionParser.train inside-root control: validates and saves without running real training."""
    TransitionParser = sandbox_env["TransitionParser"]
    inside_file = sandbox_env["sandbox_dir"] / "model.arcstd"

    parser = TransitionParser("arc-standard")

    # Intercept training and scikit-learn boundaries (no real dataset or fit)
    fake_model = MagicMock()
    with patch("tempfile.NamedTemporaryFile") as mock_tmp, \
         patch("nltk.parse.transitionparser.load_svmlight_file", return_value=(MagicMock(), MagicMock())), \
         patch("nltk.parse.transitionparser.svm.SVC", return_value=fake_model), \
         patch("nltk.parse.transitionparser.remove"):

        # Mock tempfile
        tmp_obj = MagicMock()
        tmp_obj.name = "fake_train.tmp"
        mock_tmp.return_value = tmp_obj

        # Intercept _create_training_examples so it does not iterate real graphs
        parser._create_training_examples_arc_std = MagicMock()

        # Intercept pickle.dump to avoid real model payload
        with patch("pickle.dump") as mock_dump:
            parser.train(depgraphs=[], modelfile=str(inside_file), verbose=False)
            assert mock_dump.called
            # Verify the destination file handle was opened inside sandbox
            opened_file = mock_dump.call_args[0][1]
            assert Path(opened_file.name).resolve() == inside_file.resolve()


# --- API 2: TransitionParser.parse ---

def test_transition_parser_parse_outside_refusal(sandbox_env):
    """TransitionParser.parse must refuse reading an outside-root model file."""
    TransitionParser = sandbox_env["TransitionParser"]
    outside_file = sandbox_env["outside_dir"] / "outside_model.arcstd"
    with open(outside_file, "wb") as f:
        f.write(b"dummy_payload")

    parser = TransitionParser("arc-standard")
    with patch("nltk.parse.transitionparser.allowlisted_pickle_load") as mock_unpickle:
        with pytest.raises(PermissionError, match="Security Violation"):
            parser.parse(depgraphs=[], modelFile=str(outside_file))

        # Ensure unpickling was completely prevented
        assert not mock_unpickle.called, "Unpickling must not execute on outside path"


def test_transition_parser_parse_inside_control(sandbox_env):
    """TransitionParser.parse inside-root control: routes through pathsec.open with intercepted unpickling."""
    TransitionParser = sandbox_env["TransitionParser"]
    inside_file = sandbox_env["sandbox_dir"] / "inside_model.arcstd"
    with open(inside_file, "wb") as f:
        f.write(b"dummy_inside_bytes")

    parser = TransitionParser("arc-standard")

    # Mock unpickler to return a harmless dummy model; no real unpickling executes
    dummy_model = MagicMock()
    with patch("nltk.parse.transitionparser.allowlisted_pickle_load", return_value=dummy_model) as mock_load:
        result = parser.parse(depgraphs=[], modelFile=str(inside_file))
        assert mock_load.called
        assert result == []


# --- API 3: AveragedPerceptron.save ---

def test_averaged_perceptron_save_outside_refusal(sandbox_env):
    """AveragedPerceptron.save must refuse writing weights to an outside-root file."""
    AveragedPerceptron = sandbox_env["AveragedPerceptron"]
    outside_file = sandbox_env["outside_dir"] / "weights.json"

    ap = AveragedPerceptron({"bias": {"NN": 1.5}})
    with pytest.raises(PermissionError, match="Security Violation"):
        ap.save(str(outside_file))

    assert not outside_file.exists(), "Outside weights file must not be created"


def test_averaged_perceptron_save_inside_control(sandbox_env):
    """AveragedPerceptron.save inside-root control: writes JSON weights into allowed root."""
    AveragedPerceptron = sandbox_env["AveragedPerceptron"]
    inside_file = sandbox_env["sandbox_dir"] / "weights.json"

    ap = AveragedPerceptron({"bias": {"NN": 1.5}})
    ap.save(str(inside_file))

    assert inside_file.exists()
    with open(inside_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data == {"bias": {"NN": 1.5}}


# --- API 4: AveragedPerceptron.load ---

def test_averaged_perceptron_load_outside_refusal(sandbox_env):
    """AveragedPerceptron.load must refuse loading weights from an outside-root file."""
    AveragedPerceptron = sandbox_env["AveragedPerceptron"]
    outside_file = sandbox_env["outside_dir"] / "weights.json"
    with open(outside_file, "w", encoding="utf-8") as f:
        json.dump({"bias": {"VB": 2.0}}, f)

    ap = AveragedPerceptron()
    with pytest.raises(PermissionError, match="Security Violation"):
        ap.load(str(outside_file))


def test_averaged_perceptron_load_inside_control(sandbox_env):
    """AveragedPerceptron.load inside-root control: loads JSON weights from allowed root."""
    AveragedPerceptron = sandbox_env["AveragedPerceptron"]
    inside_file = sandbox_env["sandbox_dir"] / "weights.json"
    with open(inside_file, "w", encoding="utf-8") as f:
        json.dump({"bias": {"VB": 2.0}}, f)

    ap = AveragedPerceptron()
    ap.load(str(inside_file))
    assert ap.weights == {"bias": {"VB": 2.0}}


# --- API 5: PerceptronTagger.save_to_json ---

def test_perceptron_tagger_save_to_json_outside_refusal(sandbox_env):
    """PerceptronTagger.save_to_json must refuse an outside directory and create no files."""
    PerceptronTagger = sandbox_env["PerceptronTagger"]
    outside_loc = sandbox_env["outside_dir"] / "model_dir"

    # Instantiate without loading any model (load=False)
    tagger = PerceptronTagger(load=False)
    with pytest.raises(PermissionError, match="Security Violation"):
        tagger.save_to_json(loc=str(outside_loc))

    assert not outside_loc.exists(), "Outside model directory must not be created"


def test_perceptron_tagger_save_to_json_inside_control(sandbox_env):
    """PerceptronTagger.save_to_json inside-root control: writes parameter files in allowed root."""
    PerceptronTagger = sandbox_env["PerceptronTagger"]
    inside_loc = sandbox_env["sandbox_dir"] / "model_dir"

    tagger = PerceptronTagger(load=False)
    tagger.save_to_json(loc=str(inside_loc))

    assert inside_loc.is_dir()
    for fname in tagger.param_files("xxx"):
        assert (inside_loc / fname).exists(), f"Expected parameter file {fname} to exist"


def test_perceptron_tagger_filename_traversal_refusal(sandbox_env):
    """PerceptronTagger.save_to_json refuses language strings with path traversal."""
    PerceptronTagger = sandbox_env["PerceptronTagger"]
    inside_loc = sandbox_env["sandbox_dir"] / "model_dir"

    tagger = PerceptronTagger(load=False)
    with pytest.raises(ValueError, match="Invalid tagger language code"):
        tagger.save_to_json(lang="../../escape", loc=str(inside_loc))


# --- API 6: save_maxent_params ---

def test_save_maxent_params_outside_refusal(sandbox_env):
    """save_maxent_params must refuse outside directories before creating dir or files."""
    save_maxent_params = sandbox_env["save_maxent_params"]
    outside_tab_dir = sandbox_env["outside_dir"] / "maxent_tabs"

    dummy_wgt = MagicMock()
    dummy_wgt.tolist.return_value = [0.1, 0.2]
    dummy_mpg = {("feat", "val", "label"): 0}
    dummy_lab = ["label"]
    dummy_aon = {"label": 0}

    with pytest.raises(PermissionError, match="Security Violation"):
        save_maxent_params(
            dummy_wgt, dummy_mpg, dummy_lab, dummy_aon, tab_dir=str(outside_tab_dir)
        )

    assert not outside_tab_dir.exists(), "Outside tab directory must not be created"


def test_save_maxent_params_inside_control(sandbox_env):
    """save_maxent_params inside-root control: writes all four tab files cleanly inside root."""
    save_maxent_params = sandbox_env["save_maxent_params"]
    inside_tab_dir = sandbox_env["sandbox_dir"] / "maxent_tabs"

    dummy_wgt = MagicMock()
    dummy_wgt.tolist.return_value = [0.1, 0.2]
    dummy_mpg = {("feat", "val", "label"): 0}
    dummy_lab = ["label"]
    dummy_aon = {"label": 0}

    out_dir = save_maxent_params(
        dummy_wgt, dummy_mpg, dummy_lab, dummy_aon, tab_dir=str(inside_tab_dir)
    )
    assert out_dir == str(inside_tab_dir)
    assert inside_tab_dir.is_dir()

    expected_files = ["weights.txt", "mapping.tab", "labels.txt", "alwayson.tab"]
    for f in expected_files:
        p = inside_tab_dir / f
        assert p.exists(), f"Expected tab file {f} to exist"
        assert p.stat().st_size > 0


# ==============================================================================
# Suite 3: Nested Traversal and Symlink Escape Coverage
# ==============================================================================

def test_nested_path_traversal_escape_refusal(sandbox_env):
    """Nested traversal sequences like 'sandbox/sub/../../outside' are resolved and refused."""
    AveragedPerceptron = sandbox_env["AveragedPerceptron"]
    traversal_target = (
        sandbox_env["sandbox_dir"]
        / "sub"
        / ".."
        / ".."
        / sandbox_env["outside_dir"].name
        / "weights.json"
    )

    ap = AveragedPerceptron({"bias": {"NN": 1.0}})
    with pytest.raises(PermissionError, match="Security Violation"):
        ap.save(str(traversal_target))


def test_symlink_escape_refusal_or_unprivileged_boundary(sandbox_env):
    """Test symlink escape containment, or honestly record unprivileged platform boundary."""
    AveragedPerceptron = sandbox_env["AveragedPerceptron"]
    link_in_sandbox = sandbox_env["sandbox_dir"] / "link_to_outside"

    # Attempt symlink creation
    try:
        os.symlink(str(sandbox_env["outside_dir"]), str(link_in_sandbox), target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        # Windows without Developer Mode or unprivileged user raises OSError
        pytest.skip(
            f"Symlink creation not permitted in this environment ({exc}); "
            "boundary recorded: symlink escapes require symlink creation privileges to exercise."
        )

    # If symlink was successfully created, verify pathsec catches the resolved escape
    symlink_file = link_in_sandbox / "weights.json"
    ap = AveragedPerceptron({"bias": {"NN": 1.0}})
    with pytest.raises(PermissionError, match="Security Violation"):
        ap.save(str(symlink_file))

    assert not (sandbox_env["outside_dir"] / "weights.json").exists()


# ==============================================================================
# Suite 4: Structural & Boundary Invariants
# ==============================================================================

def test_no_checkpoint_loading_or_inference_invoked():
    """Verify that test suite execution boundary holds: no torch, whisper, or real checkpoints loaded."""
    for mod in ["torch", "whisper", "whisperx", "pyannote"]:
        assert mod not in sys.modules, f"Forbidden module {mod} was imported during pathsec tests"
