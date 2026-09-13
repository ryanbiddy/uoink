# Reuse the two recorded local wheels — 2026-09-13

The smallest next step is to inspect the two existing cached wheels. Their adjacent `origin.json` records match the selected sdists' exact URLs and SHA256 values. The September 10 install log records a matching wheel filename, size and hash for each. No wheel has been opened or hashed by this proposal yet; those identities are historical claims pending the fixed read-only check.

| Selected package | Recorded source archive | Bytes | Recorded SHA256 |
|---|---|---:|---|
| ANTLR `4.9.3` | `antlr4-python3-runtime-4.9.3.tar.gz` | 117,034 | `f224469b4168294902bb1efa80a8bf7855f24c99aef99cbefc1bcd3cce77881b` |
| proxy-tools `0.1.0` | `proxy_tools-0.1.0.tar.gz` | 2,978 | `ccb3751f529c047e2d8a58440d86b205303cf0fe8146f784d1cbcd94f0a28010` |

The retained source URLs are [ANTLR's exact sdist](https://files.pythonhosted.org/packages/3e/38/7859ff46355f76f8d19459005ca000b6e7012f2f1ca597746cbcd1fbfe5e/antlr4-python3-runtime-4.9.3.tar.gz) and [proxy-tools' exact sdist](https://files.pythonhosted.org/packages/f2/cf/77d3e19b7fabd03895caca7857ef51e4c409e0ca6b37ee6e9f7daa50b642/proxy_tools-0.1.0.tar.gz). These are copied historical metadata, not new requests. Neither release entry advertises a wheel, core metadata sidecar, signature or Requires-Python value. Both are recorded as not yanked.

| Existing wheel candidate | Historical bytes | Historical SHA256 |
|---|---:|---|
| `antlr4_python3_runtime-4.9.3-py3-none-any.whl` | 144,613 | `d50ab331bff062b5e7f74e19fb16a2e891a47e893d805bcdbff8e6e6beb09c37` |
| `proxy_tools-0.1.0-py3-none-any.whl` | 2,943 | `a049f8570f5ce89b723ba282b90291ac3aa1fdcbd7d7100426ff659447400c68` |

The exact candidate paths are fixed in the inspector source. Both belong to `_scratch/python313-graph-01/cache/wheels`, as recorded in `install.stdout` lines 457–462. `install-command.json` records exit 0 on 2026-09-10, with `--no-build-isolation` and `--no-compile`. The preceding bootstrap record names pip 26.1.2, setuptools 83.0.0, wheel 0.47.0 and packaging 26.2. Its environment record identifies CPython 3.13.15 on Windows. These logs record a prior build; they do not establish a deterministic recipe, a newly verified artifact, or compatibility with the proposed runtime stack.

The exact-version install report claims BSD for ANTLR 4.9.3 and MIT for proxy-tools 0.1.0. The ANTLR PyPI file's top-level `info` describes 4.13.2 and cannot supply 4.9.3's authoritative package metadata; only its `releases['4.9.3']` entry is used for source identity here. The install report separately records 4.9.3 and its inactive-on-3.13 `typing; python_version < '3.5'` dependency. Neither current source inspection nor a complete license-text review has happened. Retain notices actually present in the wheels, and report any missing notice or metadata mismatch rather than guessing a BSD variant.

Root source review may admit one bounded inspection: first verify each whole wheel against its historical size/hash, then validate ZIP names, types, sizes, compression and extents; parse METADATA/WHEEL/RECORD as text; hash every member against RECORD; record the exact package inventory and any included license text. Do not extract an importable package tree or invoke the old interpreter. A valid inspection makes the observed wheel bytes and metadata reviewable. It does not install them or turn a historical origin claim into publisher authentication.

If both candidates match, add only their exact observed METADATA and built-artifact identities to a separately reviewed local-wheel graph branch. Keep public PyPI wheel availability false, preserve the historical sdist origin, and keep artifact-verification false in any later metadata-only graph invocation. The existing complete144 FAIL remains unchanged; a new graph run would need the documented repair and its own brief.

If a candidate is missing or differs, stop and preserve that finding. Do not rebuild automatically. The fallback is a separately reviewed acquisition of only the exact small sdist above, or reuse of an already hash-verified local copy if one is later located. Before any build, inspect the archive as inert bytes: safe member paths and types, expansion bounds, exact package/license/setup files, no execution. No separately verified current sdist file was established by this bounded text inventory. The HTTP cache was not searched or opened. A build recipe must then bind the inspected whitelist and complete notices; no guessed package membership or newer ANTLR release may substitute. Prefer a deterministic byte recipe for pure source after that inspection; do not execute setup or request build dependencies as an implicit side effect.

Eight retained text inputs and their exact copy bindings accompany this plan. The complete graph stays FAIL with the two wheel gaps until the concrete candidate bytes and the graph admission changes are reviewed. No new fetch, build, install, model import or application run occurred here.
