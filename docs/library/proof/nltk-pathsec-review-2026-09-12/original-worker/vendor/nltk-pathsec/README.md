# NLTK Pathsec Backport (GHSA-8mgp-746c-j5xp)

This directory provides the reviewed source backport patch for advisory **GHSA-8mgp-746c-j5xp** (CVE-2026-81726, PYSEC-2026-3740) against **NLTK 3.10.3** (the installed staging release).

## Vulnerability Summary

In NLTK `<= 3.10.3`, six public model-artifact persistence and loading APIs used built-in `open()`, raw `os.mkdir()`, or unverified path references on caller-supplied model paths, bypassing `nltk.pathsec` sandbox enforcement even when `pathsec.ENFORCE = True`. This allowed untrusted callers to read from or write/overwrite files outside allowed data roots via standard model loading and saving routines.

## Scope and Covered APIs

The patch `nltk-3.10.3-pathsec.patch` explicitly covers all six APIs identified in GHSA-8mgp-746c-j5xp across three source files:

1. `nltk/parse/transitionparser.py`:
   - `TransitionParser.train(self, depgraphs, modelfile, verbose=True)`:
     - Validates destination `modelfile` containment upfront via `nltk.pathsec.validate_path` before any training or temporary dataset staging occurs.
     - Routes the trained model pickle write through `nltk.pathsec.open(modelfile, "wb")` with context `'TransitionParser.train'`.
   - `TransitionParser.parse(self, depgraphs, modelFile)`:
     - Routes the model read through `nltk.pathsec.open(modelFile, "rb")` with context `'TransitionParser.parse'`.
     - Preserves safe allowlisted unpickling via `allowlisted_pickle_load`.

2. `nltk/tag/perceptron.py`:
   - `AveragedPerceptron.save(self, path)`:
     - Validates `path` upfront via `nltk.pathsec.validate_path(path)`.
     - Routes JSON model dumping through `nltk.pathsec.open(path, "w")`.
   - `AveragedPerceptron.load(self, path)`:
     - Validates `path` upfront via `nltk.pathsec.validate_path(path)`.
     - Routes JSON model loading through `nltk.pathsec.open(path, "r")`.
   - `PerceptronTagger.save_to_json(self, lang="xxx", loc=None)`:
     - Validates `lang` and model filenames against path traversal via `_validate_name_component`.
     - Validates directory `loc` upfront via `nltk.pathsec.validate_path(loc)`.
     - Refuses dynamic policy root expansion: the legacy `_authorize_private_dir` helper (which appended caller directories to `nltk.data.path`) is replaced with a safe no-op sentinel.
     - On non-POSIX (Windows): creates target directories and writes each parameter JSON file through `nltk.pathsec.open`.
     - On POSIX: pins the directory descriptor via `_open_private_model_dir`, re-validates the landed descriptor path via `_fd_realpath(fd)`, and writes each file via `os.open` with `O_NOFOLLOW | 0o600`.

3. `nltk/classify/maxent.py`:
   - `save_maxent_params(wgt, mpg, lab, aon, tab_dir="/tmp")`:
     - Validates `tab_dir` upfront via `nltk.pathsec.validate_path(tab_dir)`.
     - Creates missing intermediate directories safely via `os.makedirs(tab_dir, exist_ok=True)` only after containment validation passes.
     - Routes all four tab-file writes (`weights.txt`, `mapping.tab`, `labels.txt`, `alwayson.tab`) through `nltk.pathsec.open(..., "w", newline="")`.

## Security & Path Integrity Guarantees

- **No API disabling**: All six APIs remain available with identical signatures and return semantics for authorized paths.
- **No policy root expansion**: `_authorize_private_dir` is eliminated as a sandbox widening vector; caller paths are strictly checked against existing authorized roots (`_get_allowed_roots()`).
- **No policy bypass**: `pathsec.ENFORCE` is preserved; no flag is overridden or turned off.
- **Symlink and traversal safety**:
  - All paths resolve symlinks through `Path.resolve()` in `validate_path()`.
  - On POSIX, `pathsec.open` uses `_hardened_open` with `O_NOFOLLOW` and kernel `_fd_realpath` descriptor validation.
  - Directory opens in `PerceptronTagger` re-verify the real descriptor target before writing.

## Honest Assessment of Unaffected and Unresolved Paths

### Unaffected Paths
- **`load_maxent_params`**: Already safe in NLTK 3.10.3 because it delegates to `nltk.data.open_datafile()`, which validates all inputs through `pathsec.open()`.
- **`PerceptronTagger.load_from_json`**: Already routed through `nltk.data.open_datafile()`; explicit validation was added for defense-in-depth, and `_authorize_private_dir` widening was removed.
- **`nltk.data.load`**: Uses internal resource resolution through `find()` and `restricted_pickle_load()`, which is already pathsec-guarded.

### Unresolved Upstream Edge Cases
- **`Maxent_NE_Chunker.save_params` and `build_model`** (`nltk/chunk/named_entity.py`):
  In 3.10.3, `Maxent_NE_Chunker.save_params()` hardcodes `tab_dir=f"/tmp/english_ace_{fmt}/"`. Because `save_maxent_params` now validates `tab_dir` under pathsec, calling `save_params()` will fail closed under `ENFORCE=True` unless `/tmp/english_ace_*` is explicitly added to allowed roots or `save_params()` is adapted in an expanded packaging update.
- **Subprocess-based taggers** (`CRFTagger`, `StanfordTagger`, `HunposTagger`):
  These pass paths to external binaries (Java, C extensions, or CLI binaries) where `pathsec.open` cannot wrap file descriptors. Upstream PR #3813 introduces `validate_tool_path` for these components. They are outside the six model-artifact APIs designated by GHSA-8mgp-746c-j5xp and this bounded brief.
- **Nonexistent release NLTK 3.10.4**:
  No official 3.10.4 release exists on PyPI or GitHub at this time. This backport targets the true 3.10.3 release line without assuming or inventing upstream version tags.

## Application Instructions

```bash
# Deterministic application via prepare utility:
python scripts/prepare_nltk_pathsec_backport.py --src <staging_nltk_dir> --dst <target_nltk_dir>

# Direct git apply:
git apply --directory=<nltk_package_parent> vendor/nltk-pathsec/nltk-3.10.3-pathsec.patch
```
