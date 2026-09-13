#!/usr/bin/env python3
"""Deterministic preparation utility for NLTK pathsec backport (GHSA-8mgp-746c-j5xp).

Checks exact original input hashes against NLTK 3.10.3 before copying and patching
a source tree into an explicitly new destination.

Constraints:
- Never imports the input package (nltk).
- Never writes to or alters staging.
- Never fetches remote resources or accesses the network.
- Never accepts path traversal (..).
- Never overwrites an existing destination.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Verify that nltk is never imported
if "nltk" in sys.modules:
    sys.exit("Error: nltk must never be imported in this preparation utility.")

EXPECTED_VERSION = "3.10.3"

# Exact SHA-256 hashes for NLTK 3.10.3 inputs
EXPECTED_ORIGINAL_HASHES: dict[str, str] = {
    os.path.normpath("parse/transitionparser.py"): "ed55985d08ed38333d007c5e5c19170a4dc19009e871ab616d198a3da92eea70",
    os.path.normpath("tag/perceptron.py"): "9d619a5ce7533c7eb388a70fedca8dcf0fb78279e1744e2abfdfcca9abd459ea",
    os.path.normpath("classify/maxent.py"): "11f704cf6cd2a43b51cb13634e9cdbc46b0e8394e1e291e9b66036d6a59c2583",
}

COVERED_APIS = [
    "TransitionParser.train",
    "TransitionParser.parse",
    "AveragedPerceptron.save",
    "AveragedPerceptron.load",
    "PerceptronTagger.save_to_json",
    "save_maxent_params",
]


def sha256_file(path: str | Path) -> str:
    """Compute sha256 digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def validate_destination_path(dst_path: str | Path, src_path: str | Path) -> Path:
    """Validate that the destination path is safe and non-existent."""
    dst_str = str(dst_path)
    if not dst_str or not dst_str.strip():
        raise ValueError("Destination path must not be empty.")

    raw_p = Path(dst_str)
    # Refuse path traversal in components
    parts = raw_p.parts
    if ".." in parts:
        raise ValueError(f"Path traversal detected in destination path: {dst_str}")

    resolved_dst = raw_p.resolve()
    resolved_src = Path(src_path).resolve()

    if resolved_dst.exists():
        raise FileExistsError(
            f"Destination already exists: {resolved_dst}. Refusing to overwrite."
        )

    # Cannot write inside or equal to src
    if resolved_dst == resolved_src or resolved_dst.is_relative_to(resolved_src):
        raise ValueError(
            f"Destination {resolved_dst} cannot be inside or equal to source {resolved_src}."
        )

    return resolved_dst


def validate_source_tree(src_path: str | Path) -> Path:
    """Validate that source tree exists, is NLTK 3.10.3, and matches hashes."""
    resolved_src = Path(src_path).resolve()
    if not resolved_src.is_dir():
        raise FileNotFoundError(f"Source directory not found: {resolved_src}")

    # Check VERSION
    version_file = resolved_src / "VERSION"
    if not version_file.is_file():
        raise FileNotFoundError(f"VERSION file not found in source: {version_file}")

    with open(version_file, "r", encoding="utf-8") as vf:
        version = vf.read().strip()

    if version != EXPECTED_VERSION:
        raise ValueError(
            f"Unsupported source version '{version}'. Expected exactly '{EXPECTED_VERSION}'."
        )

    # Check original hashes
    observed_hashes: dict[str, str] = {}
    for rel_path, expected_hash in EXPECTED_ORIGINAL_HASHES.items():
        full_path = resolved_src / rel_path
        if not full_path.is_file():
            raise FileNotFoundError(f"Required source file missing: {full_path}")
        observed = sha256_file(full_path)
        observed_hashes[rel_path] = observed
        if observed != expected_hash:
            raise ValueError(
                f"Source hash mismatch for {rel_path}!\n"
                f"  Expected: {expected_hash}\n"
                f"  Observed: {observed}"
            )

    return resolved_src


def apply_declarative_patch(dst_dir: Path) -> dict[str, str]:
    """Apply exact declarative replacements to the copied source tree in dst_dir."""
    # 1. Patch classify/maxent.py
    maxent_path = dst_dir / "classify" / "maxent.py"
    with open(maxent_path, "r", encoding="utf-8") as f:
        maxent_content = f.read()

    orig_maxent_block = (
        'def save_maxent_params(wgt, mpg, lab, aon, tab_dir="/tmp"):\n\n'
        '    from os import mkdir\n'
        '    from os.path import isdir\n\n'
        '    from nltk.tabdata import MaxentEncoder\n\n'
        '    menc = MaxentEncoder()\n'
        '    if not isdir(tab_dir):\n'
        '        mkdir(tab_dir)\n\n'
        '    print(f"Saving Maxent parameters in {tab_dir}")\n\n'
        '    with open(f"{tab_dir}/weights.txt", "w") as f:\n'
        '        f.write(f"{menc.list2txt(map(repr, wgt.tolist()))}")\n'
        '    with open(f"{tab_dir}/mapping.tab", "w") as f:\n'
        '        f.write(f"{menc.tupdict2tab(mpg)}")\n'
        '    with open(f"{tab_dir}/labels.txt", "w") as f:\n'
        '        f.write(f"{menc.list2txt(lab)}")\n'
        '    with open(f"{tab_dir}/alwayson.tab", "w") as f:\n'
        '        f.write(f"{menc.ivdict2tab(aon)}")'
    )

    patched_maxent_block = (
        'def save_maxent_params(wgt, mpg, lab, aon, tab_dir="/tmp"):\n\n'
        '    import os\n'
        '    from os.path import isdir\n\n'
        '    from nltk.pathsec import open as pathsec_open, validate_path\n'
        '    from nltk.tabdata import MaxentEncoder\n\n'
        '    menc = MaxentEncoder()\n'
        '    validate_path(tab_dir, context="save_maxent_params")\n'
        '    if not isdir(tab_dir):\n'
        '        os.makedirs(tab_dir, exist_ok=True)\n\n'
        '    print(f"Saving Maxent parameters in {tab_dir}")\n\n'
        '    with pathsec_open(f"{tab_dir}/weights.txt", "w", context="save_maxent_params", newline="") as f:\n'
        '        f.write(f"{menc.list2txt(map(repr, wgt.tolist()))}")\n'
        '    with pathsec_open(f"{tab_dir}/mapping.tab", "w", context="save_maxent_params", newline="") as f:\n'
        '        f.write(f"{menc.tupdict2tab(mpg)}")\n'
        '    with pathsec_open(f"{tab_dir}/labels.txt", "w", context="save_maxent_params", newline="") as f:\n'
        '        f.write(f"{menc.list2txt(lab)}")\n'
        '    with pathsec_open(f"{tab_dir}/alwayson.tab", "w", context="save_maxent_params", newline="") as f:\n'
        '        f.write(f"{menc.ivdict2tab(aon)}")\n'
        '    return tab_dir'
    )

    if orig_maxent_block not in maxent_content:
        raise ValueError("Cannot locate exact target block in classify/maxent.py")
    maxent_content = maxent_content.replace(orig_maxent_block, patched_maxent_block, 1)
    with open(maxent_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(maxent_content)

    # 2. Patch parse/transitionparser.py
    tp_path = dst_dir / "parse" / "transitionparser.py"
    with open(tp_path, "r", encoding="utf-8") as f:
        tp_content = f.read()

    orig_tp_import = (
        'from nltk.parse import DependencyEvaluator, DependencyGraph, ParserI\n'
        'from nltk.picklesec import allowlisted_pickle_load'
    )
    patched_tp_import = (
        'from nltk.parse import DependencyEvaluator, DependencyGraph, ParserI\n'
        'from nltk.pathsec import open as pathsec_open\n'
        'from nltk.pathsec import validate_path\n'
        'from nltk.picklesec import allowlisted_pickle_load'
    )
    if orig_tp_import not in tp_content:
        raise ValueError("Cannot locate import block in parse/transitionparser.py")
    tp_content = tp_content.replace(orig_tp_import, patched_tp_import, 1)

    orig_tp_train = (
        '    def train(self, depgraphs, modelfile, verbose=True):\n'
        '        """\n'
        '        :param depgraphs : list of DependencyGraph as the training data\n'
        '        :type depgraphs : DependencyGraph\n'
        '        :param modelfile : file name to save the trained model\n'
        '        :type modelfile : str\n'
        '        """\n\n'
        '        try:'
    )
    patched_tp_train = (
        '    def train(self, depgraphs, modelfile, verbose=True):\n'
        '        """\n'
        '        :param depgraphs : list of DependencyGraph as the training data\n'
        '        :type depgraphs : DependencyGraph\n'
        '        :param modelfile : file name to save the trained model\n'
        '        :type modelfile : str\n'
        '        """\n'
        '        validate_path(modelfile, context="TransitionParser.train")\n\n'
        '        try:'
    )
    if orig_tp_train not in tp_content:
        raise ValueError("Cannot locate train signature in parse/transitionparser.py")
    tp_content = tp_content.replace(orig_tp_train, patched_tp_train, 1)

    orig_tp_save = (
        '            model.fit(x_train, y_train)\n'
        '            # Save the model to file name (as pickle)\n'
        '            pickle.dump(model, open(modelfile, "wb"))\n'
        '        finally:'
    )
    patched_tp_save = (
        '            model.fit(x_train, y_train)\n'
        '            # Save the model to file name (as pickle)\n'
        '            with pathsec_open(modelfile, "wb", context="TransitionParser.train") as f:\n'
        '                pickle.dump(model, f)\n'
        '        finally:'
    )
    if orig_tp_save not in tp_content:
        raise ValueError("Cannot locate train pickle.dump in parse/transitionparser.py")
    tp_content = tp_content.replace(orig_tp_save, patched_tp_save, 1)

    orig_tp_parse = (
        '        with open(modelFile, "rb") as f:\n'
        '            model = allowlisted_pickle_load('
    )
    patched_tp_parse = (
        '        with pathsec_open(modelFile, "rb", context="TransitionParser.parse") as f:\n'
        '            model = allowlisted_pickle_load('
    )
    if orig_tp_parse not in tp_content:
        raise ValueError("Cannot locate parse modelFile open in parse/transitionparser.py")
    tp_content = tp_content.replace(orig_tp_parse, patched_tp_parse, 1)

    with open(tp_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(tp_content)

    # 3. Patch tag/perceptron.py
    perc_path = dst_dir / "tag" / "perceptron.py"
    with open(perc_path, "r", encoding="utf-8") as f:
        perc_content = f.read()

    orig_perc_import = (
        'from nltk import jsontags\n'
        'from nltk.data import FileSystemPathPointer, find, open_datafile\n'
        'from nltk.tag.api import TaggerI'
    )
    patched_perc_import = (
        'from nltk import jsontags\n'
        'from nltk.data import FileSystemPathPointer, find, open_datafile\n'
        'from nltk.pathsec import _fd_realpath\n'
        'from nltk.pathsec import open as pathsec_open\n'
        'from nltk.pathsec import validate_path\n'
        'from nltk.tag.api import TaggerI\n\n\n'
        'def _validate_name_component(value, kind="language code"):\n'
        '    """Refuse a value that is really a path where a filename fragment is meant."""\n'
        '    text = str(value)\n'
        '    if (\n'
        '        not text\n'
        '        or not text.strip()\n'
        '        or text in (".", "..")\n'
        '        or "\\x00" in text\n'
        '        or "/" in text\n'
        '        or "\\\\" in text\n'
        '        or os.sep in text\n'
        '        or (os.altsep and os.altsep in text)\n'
        '    ):\n'
        '        raise ValueError(\n'
        '            f"Invalid tagger {kind} {value!r}: must be a single filename "\n'
        '            "component (no path separators, \'..\' or NUL)"\n'
        '        )\n'
        '    return text'
    )
    if orig_perc_import not in perc_content:
        raise ValueError("Cannot locate import block in tag/perceptron.py")
    perc_content = perc_content.replace(orig_perc_import, patched_perc_import, 1)

    orig_perc_auth = (
        'def _authorize_private_dir(directory):\n'
        '    """Register a private, user-owned trained-model directory on nltk.data.path\n'
        '    so the pathsec sandbox permits reading a saved model back from it.\n'
        '\n'
        '    The default trained-tagger location is the system temp dir, which is shared\n'
        '    and world-writable on Linux. A directory that is private to the current user\n'
        '    (not group-/world-writable) cannot be tampered with by another local user, so\n'
        '    it is safe to trust; a world-writable one is deliberately NOT authorized and\n'
        '    stays refused (CWE-377/CWE-378).\n'
        '    """\n'
        '    import nltk.data\n'
        '    from nltk import pathsec\n'
        '\n'
        '    try:\n'
        '        real = os.path.realpath(str(directory))\n'
        '    except (OSError, ValueError):\n'
        '        return\n'
        '    if not pathsec.is_private_dir(real):\n'
        '        return\n'
        '    known = [os.path.realpath(str(p)) for p in nltk.data.path if isinstance(p, str)]\n'
        '    if real not in known:\n'
        '        nltk.data.path.append(real)\n'
        '        pathsec._ALLOWED_ROOTS_CACHE = None\n'
        '        pathsec._LAST_DATA_PATHS = None'
    )
    patched_perc_auth = (
        'def _authorize_private_dir(directory):\n'
        '    """Retained for backward compatibility as a no-op sentinel.\n'
        '    Dynamic sandbox widening is disallowed under GHSA-8mgp-746c-j5xp.\n'
        '    """\n'
        '    return'
    )
    if orig_perc_auth not in perc_content:
        raise ValueError("Cannot locate _authorize_private_dir in tag/perceptron.py")
    perc_content = perc_content.replace(orig_perc_auth, patched_perc_auth, 1)

    orig_perc_open_priv = (
        '        if os.name == "posix" and (st.st_uid != os.getuid() or (st.st_mode & 0o022)):\n'
        '            raise PermissionError(\n'
        '                f"Refusing non-private trained-model dir {loc!r}: not owned by "\n'
        '                "you or group-/world-writable (CWE-377/378)"\n'
        '            )\n'
        '    except BaseException:\n'
        '        os.close(fd)\n'
        '        raise\n'
        '    return fd'
    )
    patched_perc_open_priv = (
        '        if os.name == "posix" and (st.st_uid != os.getuid() or (st.st_mode & 0o022)):\n'
        '            raise PermissionError(\n'
        '                f"Refusing non-private trained-model dir {loc!r}: not owned by "\n'
        '                "you or group-/world-writable (CWE-377/378)"\n'
        '            )\n'
        '        landed = _fd_realpath(fd)\n'
        '        validate_path(\n'
        '            landed if landed is not None else os.path.realpath(loc),\n'
        '            context="PerceptronTagger.save_to_json",\n'
        '        )\n'
        '    except BaseException:\n'
        '        os.close(fd)\n'
        '        raise\n'
        '    return fd'
    )
    if orig_perc_open_priv not in perc_content:
        raise ValueError("Cannot locate _open_private_model_dir checks in tag/perceptron.py")
    perc_content = perc_content.replace(orig_perc_open_priv, patched_perc_open_priv, 1)

    orig_ap_saveload = (
        '    def save(self, path):\n'
        '        """Save the model weights as json"""\n'
        '        with open(path, "w") as fout:\n'
        '            return json.dump(self.weights, fout)\n'
        '\n'
        '    def load(self, path):\n'
        '        """Load the json model weights."""\n'
        '        with open(path) as fin:\n'
        '            self.weights = json.load(fin)'
    )
    patched_ap_saveload = (
        '    def save(self, path):\n'
        '        """Save the model weights as json"""\n'
        '        validate_path(path, context="AveragedPerceptron.save")\n'
        '        with pathsec_open(path, "w", context="AveragedPerceptron.save") as fout:\n'
        '            return json.dump(self.weights, fout)\n'
        '\n'
        '    def load(self, path):\n'
        '        """Load the json model weights."""\n'
        '        validate_path(path, context="AveragedPerceptron.load")\n'
        '        with pathsec_open(path, "r", context="AveragedPerceptron.load") as fin:\n'
        '            self.weights = json.load(fin)'
    )
    if orig_ap_saveload not in perc_content:
        raise ValueError("Cannot locate AveragedPerceptron save/load in tag/perceptron.py")
    perc_content = perc_content.replace(orig_ap_saveload, patched_ap_saveload, 1)

    orig_pt_params = (
        '    def param_files(self, lang="eng"):\n'
        '        return (\n'
        '            f"{self.TAGGER_NAME}_{lang}.{attr}.json"\n'
        '            for attr in ["weights", "tagdict", "classes"]\n'
        '        )'
    )
    patched_pt_params = (
        '    def param_files(self, lang="eng"):\n'
        '        _validate_name_component(lang, "language code")\n'
        '        return (\n'
        '            _validate_name_component(\n'
        '                f"{self.TAGGER_NAME}_{lang}.{attr}.json", "model filename"\n'
        '            )\n'
        '            for attr in ["weights", "tagdict", "classes"]\n'
        '        )'
    )
    if orig_pt_params not in perc_content:
        raise ValueError("Cannot locate PerceptronTagger.param_files in tag/perceptron.py")
    perc_content = perc_content.replace(orig_pt_params, patched_pt_params, 1)

    orig_pt_save = (
        '    def save_to_json(self, lang="xxx", loc=None):\n'
        '        if not loc:\n'
        '            loc = self.save_dir\n'
        '        # On POSIX the default TRAINED_TAGGER_PATH is a shared, world-writable\n'
        '        # temp dir (/tmp) and the save dir is a *guessable* name in it, so a\n'
        '        # local attacker can pre-plant or race a symlink at ``loc``. A plain\n'
        '        # ``islink`` pre-check is non-atomic (TOCTOU) and misses it once created;\n'
        '        # ``_open_private_model_dir`` instead creates/re-opens the leaf atomically\n'
        '        # with O_NOFOLLOW|O_DIRECTORY, verifies it is a real, user-owned,\n'
        '        # non-world-writable directory, and returns a pinned fd we write relative\n'
        '        # to (CWE-59/377/378).\n'
        '        #\n'
        '        # On Windows ``%TEMP%`` is per-user and ACL-protected (no such squat), and\n'
        '        # ``os.open`` cannot open a directory as a descriptor there, so use a\n'
        '        # plain create + write.\n'
        '        if os.name != "posix":\n'
        '            os.makedirs(loc, exist_ok=True)\n'
        '            _authorize_private_dir(loc)\n'
        '            for param, json_file in zip(self.encode_json_obj(), self.param_files(lang)):\n'
        '                with open(path_join(loc, json_file), "w") as fout:\n'
        '                    json.dump(param, fout)\n'
        '            return\n'
        '\n'
        '        dir_fd = _open_private_model_dir(loc)\n'
        '        try:\n'
        '            _authorize_private_dir(loc)\n'
        '\n'
        '            # Write each model file relative to the pinned directory fd (where\n'
        '            # supported) with O_NOFOLLOW (0600), so neither the dir nor the file\n'
        '            # can be redirected outside the verified directory after the check.\n'
        '            use_dir_fd = os.open in os.supports_dir_fd\n'
        '\n'
        '            def _no_follow_opener(path, flags):\n'
        '                extra = {"dir_fd": dir_fd} if use_dir_fd else {}\n'
        '                return os.open(\n'
        '                    path, flags | getattr(os, "O_NOFOLLOW", 0), 0o600, **extra\n'
        '                )\n'
        '\n'
        '            for param, json_file in zip(self.encode_json_obj(), self.param_files(lang)):\n'
        '                target = json_file if use_dir_fd else path_join(loc, json_file)\n'
        '                with open(target, "w", opener=_no_follow_opener) as fout:\n'
        '                    json.dump(param, fout)\n'
        '        finally:\n'
        '            os.close(dir_fd)'
    )
    patched_pt_save = (
        '    def save_to_json(self, lang="xxx", loc=None):\n'
        '        _validate_name_component(lang, "language code")\n'
        '        if not loc:\n'
        '            loc = self.save_dir\n'
        '        validate_path(loc, context="PerceptronTagger.save_to_json")\n'
        '        # On POSIX the default TRAINED_TAGGER_PATH is a shared, world-writable\n'
        '        # temp dir (/tmp) and the save dir is a *guessable* name in it, so a\n'
        '        # local attacker can pre-plant or race a symlink at ``loc``. A plain\n'
        '        # ``islink`` pre-check is non-atomic (TOCTOU) and misses it once created;\n'
        '        # ``_open_private_model_dir`` instead creates/re-opens the leaf atomically\n'
        '        # with O_NOFOLLOW|O_DIRECTORY, verifies it is a real, user-owned,\n'
        '        # non-world-writable directory, and returns a pinned fd we write relative\n'
        '        # to (CWE-59/377/378).\n'
        '        #\n'
        '        # On Windows ``%TEMP%`` is per-user and ACL-protected (no such squat), and\n'
        '        # ``os.open`` cannot open a directory as a descriptor there, so use a\n'
        '        # plain create + write.\n'
        '        if os.name != "posix":\n'
        '            os.makedirs(loc, exist_ok=True)\n'
        '            for param, json_file in zip(self.encode_json_obj(), self.param_files(lang)):\n'
        '                with pathsec_open(\n'
        '                    path_join(loc, json_file),\n'
        '                    "w",\n'
        '                    context="PerceptronTagger.save_to_json",\n'
        '                ) as fout:\n'
        '                    json.dump(param, fout)\n'
        '            return\n'
        '\n'
        '        dir_fd = _open_private_model_dir(loc)\n'
        '        try:\n'
        '            # Write each model file relative to the pinned directory fd (where\n'
        '            # supported) with O_NOFOLLOW (0600), so neither the dir nor the file\n'
        '            # can be redirected outside the verified directory after the check.\n'
        '            use_dir_fd = os.open in os.supports_dir_fd\n'
        '\n'
        '            def _no_follow_opener(path, flags):\n'
        '                extra = {"dir_fd": dir_fd} if use_dir_fd else {}\n'
        '                return os.open(\n'
        '                    path, flags | getattr(os, "O_NOFOLLOW", 0), 0o600, **extra\n'
        '                )\n'
        '\n'
        '            for param, json_file in zip(self.encode_json_obj(), self.param_files(lang)):\n'
        '                target = json_file if use_dir_fd else path_join(loc, json_file)\n'
        '                fd = _no_follow_opener(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)\n'
        '                with os.fdopen(fd, "w") as fout:\n'
        '                    json.dump(param, fout)\n'
        '        finally:\n'
        '            os.close(dir_fd)'
    )
    if orig_pt_save not in perc_content:
        raise ValueError("Cannot locate PerceptronTagger.save_to_json in tag/perceptron.py")
    perc_content = perc_content.replace(orig_pt_save, patched_pt_save, 1)

    orig_pt_load = (
        '    def load_from_json(self, lang="eng", loc=None):\n'
        '        # Automatically find path to the tagger if location is not specified.\n'
        '        # loc can refer to zip or real FS\n'
        '        if loc is None:\n'
        '            loc = find(f"taggers/averaged_perceptron_tagger_{lang}/")\n'
        '        elif isinstance(loc, str):\n'
        '            # Backward compatible:\n'
        '            # - absolute paths are explicit filesystem locations\n'
        '            # - relative strings are treated as NLTK resource names and resolved via find()\n'
        '            if os.path.isabs(loc):\n'
        '                loc = FileSystemPathPointer(loc)\n'
        '            else:\n'
        '                loc = find(loc)\n'
        '        elif isinstance(loc, Path):\n'
        '            # Explicit filesystem path\n'
        '            loc = FileSystemPathPointer(str(loc))\n'
        '        # else: assume loc is already a PathPointer (zip or filesystem)\n'
        '\n'
        '        # A trained model saved under the (private) system-temp trained-tagger\n'
        '        # dir lives outside nltk_data; authorize that specific private directory\n'
        '        # so it can be read back under the pathsec sandbox.\n'
        '        loc_path = getattr(loc, "path", None)\n'
        '        if loc_path and os.path.isdir(loc_path):\n'
        '            _authorize_private_dir(loc_path)\n'
        '\n'
        '        def load_param(json_file):\n'
        '            with open_datafile(loc, json_file) as fin:\n'
        '                return json.load(fin)'
    )
    patched_pt_load = (
        '    def load_from_json(self, lang="eng", loc=None):\n'
        '        # Automatically find path to the tagger if location is not specified.\n'
        '        # loc can refer to zip or real FS\n'
        '        _validate_name_component(lang, "language code")\n'
        '        if loc is None:\n'
        '            loc = find(f"taggers/averaged_perceptron_tagger_{lang}/")\n'
        '        elif isinstance(loc, str):\n'
        '            # Backward compatible:\n'
        '            # - absolute paths are explicit filesystem locations\n'
        '            # - relative strings are treated as NLTK resource names and resolved via find()\n'
        '            if os.path.isabs(loc):\n'
        '                validate_path(loc, context="PerceptronTagger.load_from_json")\n'
        '                loc = FileSystemPathPointer(loc)\n'
        '            else:\n'
        '                loc = find(loc)\n'
        '        elif isinstance(loc, Path):\n'
        '            # Explicit filesystem path\n'
        '            validate_path(str(loc), context="PerceptronTagger.load_from_json")\n'
        '            loc = FileSystemPathPointer(str(loc))\n'
        '        # else: assume loc is already a PathPointer (zip or filesystem)\n'
        '\n'
        '        def load_param(json_file):\n'
        '            with open_datafile(loc, json_file) as fin:\n'
        '                return json.load(fin)'
    )
    if orig_pt_load not in perc_content:
        raise ValueError("Cannot locate PerceptronTagger.load_from_json in tag/perceptron.py")
    perc_content = perc_content.replace(orig_pt_load, patched_pt_load, 1)

    with open(perc_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(perc_content)

    # Compute patched hashes
    patched_hashes: dict[str, str] = {}
    for rel_path in EXPECTED_ORIGINAL_HASHES:
        patched_hashes[rel_path] = sha256_file(dst_dir / rel_path)

    return patched_hashes


def prepare_backport(
    src: str | Path,
    dst: str | Path,
    patch_file: str | Path | None = None,
    receipt_path: str | Path | None = None,
) -> dict:
    """Execute the full backport preparation pipeline deterministically."""
    # 1. Validate inputs
    src_dir = validate_source_tree(src)
    dst_dir = validate_destination_path(dst, src_dir)

    default_patch = (
        Path(__file__).resolve().parent.parent
        / "vendor"
        / "nltk-pathsec"
        / "nltk-3.10.3-pathsec.patch"
    )
    patch_path = Path(patch_file) if patch_file else default_patch
    if not patch_path.is_file():
        raise FileNotFoundError(f"Patch file not found: {patch_path}")
    patch_sha256 = sha256_file(patch_path)

    # 2. Copy source tree to new destination
    shutil.copytree(src_dir, dst_dir)

    # 3. Apply exact declarative patch
    patched_hashes = apply_declarative_patch(dst_dir)

    # 4. Construct truthful preparation receipt
    receipt = {
        "status": "SUCCESS",
        "advisory": "GHSA-8mgp-746c-j5xp",
        "target_version": EXPECTED_VERSION,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source_directory": str(src_dir),
        "destination_directory": str(dst_dir),
        "patch_file": str(patch_path),
        "patch_sha256": patch_sha256,
        "original_hashes": EXPECTED_ORIGINAL_HASHES,
        "patched_hashes": patched_hashes,
        "covered_apis": COVERED_APIS,
    }

    if receipt_path:
        out_receipt = Path(receipt_path).resolve()
        out_receipt.parent.mkdir(parents=True, exist_ok=True)
        with open(out_receipt, "w", encoding="utf-8") as rf:
            json.dump(receipt, rf, indent=2)
            rf.write("\n")

    return receipt


def main():
    parser = argparse.ArgumentParser(
        description="Deterministic preparation utility for NLTK pathsec backport (GHSA-8mgp-746c-j5xp)."
    )
    default_staging = Path(
        "E:/AI/projects/uoink/checkouts/Yoink-library/installer/staging/python/Lib/site-packages/nltk"
    )
    parser.add_argument(
        "--src",
        default=str(default_staging) if default_staging.is_dir() else None,
        required=not default_staging.is_dir(),
        help="Path to clean, unpatched NLTK 3.10.3 source directory.",
    )
    parser.add_argument(
        "--dst",
        required=True,
        help="Path to explicitly new destination directory.",
    )
    parser.add_argument(
        "--patch-file",
        default=None,
        help="Optional path to unified diff patch file.",
    )
    parser.add_argument(
        "--receipt",
        default=None,
        help="Optional path to write receipt JSON file.",
    )

    args = parser.parse_args()

    try:
        receipt = prepare_backport(
            src=args.src,
            dst=args.dst,
            patch_file=args.patch_file,
            receipt_path=args.receipt,
        )
        print("NLTK Pathsec Backport Preparation Successful!")
        print(f"  Source:      {receipt['source_directory']}")
        print(f"  Destination: {receipt['destination_directory']}")
        print(f"  Patch Hash:  {receipt['patch_sha256']}")
        print("  Patched file hashes:")
        for k, v in receipt["patched_hashes"].items():
            print(f"    {k}: {v}")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
