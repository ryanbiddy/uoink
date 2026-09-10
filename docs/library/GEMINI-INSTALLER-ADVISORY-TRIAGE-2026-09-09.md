# Installer Dependency Advisory Triage Report, 2026-09-09

This report provides the bounded read-only security triage requested in `docs/library/RYAN-INSTALLER-ADVISORY-TRIAGE-BRIEF-2026-09-09.md`. It evaluates the 95 raw OSV advisory records reported against the 142 pinned packages in `requirements-installer-lock.txt`, investigates reachability across Uoink first-party code and bundled runtime libraries, and analyzes compatibility against the PyPI dependency graph.

---

## 1. Executive Summary and Advisory Disambiguation

The initial OSV query batch (`docs/library/proof/ryan-security-council-ab-2026-09-09/installer-osv-01/summary.json`) flagged seven packages with 95 advisory matches.

The raw count of 95 reflects redundant cross-database entries (GitHub Reviewed Advisories `GHSA-*`, PyPA Advisory Database records `PYSEC-*`, and NIST Common Vulnerabilities and Exposures `CVE-*`). Resolving aliases into connected components reveals **55 distinct issues**. No advisory in the set is marked `withdrawn`.

| Package | Pinned Version | Raw OSV Matches | Distinct Issues | Feasible Patched Version | Upstream / Graph Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **cryptography** | 49.0.0 | 2 | 1 | 50.0.1 | Feasible safe upgrade; satisfies `pyopenssl<51,>=49.0.0`. |
| **lightning** | 2.6.5 | 2 | 1 | None on PyPI | Upstream unfixed on PyPI; `2022.6.15` fixed event is an advisory database error. |
| **mcp** | 1.27.1 | 6 | 3 | 1.28.1 | Feasible upgrade; requires Phase 5 SDK integration test validation. |
| **nltk** | 3.10.0 | 35 | 20 | 3.10.3 | Feasible safe upgrade; satisfies `whisperx>=3.9.1`. |
| **pillow** | 10.4.0 | 34 | 17 | 12.3.0 | Feasible safe upgrade; fixes reachable image parser memory corruptions. |
| **torch** | 2.8.0 | 8 | 8 | None (2.8.x) | Blocked by runtime graph (`whisperx 3.8.6 -> torch~=2.8.0`). No 2.8.1 on PyPI. |
| **transformers** | 4.57.6 | 8 | 5 | None (4.x) | Blocked by runtime graph (5.x requires `huggingface-hub>=1.3.0`, conflicting with `whisperx<1.0.0`). |
| **Total** | | **95** | **55** | | |

---

## 2. Package-by-Package Advisory Triage and Alias Mapping

### 2.1 cryptography 49.0.0 (2 matches, 1 distinct issue)

* **Issue 1 (CVE-2026-69247)**:
  * **Aliases**: `GHSA-g6cj-pr64-35w5`, `PYSEC-2026-3552`, `CGA-g67v-j9r6-8vjv`.
  * **Summary**: PKCS#7 `EnvelopedData` decryption exposes a Bleichenbacher oracle through distinguishable error messages and processing timing.
  * **Affected Ranges**: `introduced: 44.0.0`, `fixed: 50.0.0`.
  * **Contradictory Metadata**: None. Both GHSA and PYSEC report identical version ranges and CWE classifications (CWE-208, CWE-209).
  * **Withdrawn**: No.

### 2.2 lightning 2.6.5 (2 matches, 1 distinct issue)

* **Issue 1 (CVE-2026-58659)**:
  * **Aliases**: `GHSA-qqmf-gpg7-g8gw`, `PYSEC-2026-3624`.
  * **Summary**: Arbitrary code execution in `_load_state` via checkpoint `_instantiator` hyperparameters during `LightningModule.load_from_checkpoint`. Crafted checkpoints bypass `weights_only=True`.
  * **Affected Ranges**:
    * `GHSA-qqmf-gpg7-g8gw`: `introduced: 0`, `fixed: 2022.6.15`.
    * `PYSEC-2026-3624`: `introduced: 0`, no fixed event recorded (lists all versions through 2.6.5).
  * **Contradictory Metadata and Fixed-Version Analysis**:
    * The advisory prose explicitly states: *"PyTorch Lightning through 2.6.5, fixed in commit d710d68..."*.
    * On PyPI, package `lightning` has 171 releases, ending at `2.6.5`. Release `2022.6.15` does not exist on PyPI. Package `pytorch-lightning` similarly has 222 releases ending at `2.6.5` with no `2022.6.15` release.
    * The string `2022.6.15` is a calendar date string mistakenly ingested as an ecosystem version event in the GitHub Advisory Database. Because PEP 440 sorts `2022.6.15` higher than `2.6.5`, naive scanners report false negatives or attempt to install a nonexistent release.
    * Commit `d710d689510d50e800f53b3cd773cbca20b1f86f` is merged into upstream git, but Lightning AI has not cut a PyPI release (e.g. 2.6.6 or 2.7.0). This issue is **upstream-unfixed on PyPI**.
  * **Withdrawn**: No.

### 2.3 mcp 1.27.1 (6 matches, 3 distinct issues)

* **Issue 1 (CVE-2026-52870)**:
  * **Aliases**: `GHSA-hvrp-rf83-w775`, `PYSEC-2026-3481`.
  * **Summary**: Experimental task handlers allow any client to access and cancel tasks created by other clients.
  * **Affected Ranges**: `introduced: 0`, `fixed: 1.27.2`.
  * **Contradictory Metadata**: None. Both report fixed in 1.27.2.
  * **Withdrawn**: No.
* **Issue 2 (CVE-2026-52869)**:
  * **Aliases**: `GHSA-jpw9-pfvf-9f58`, `PYSEC-2026-3482`.
  * **Summary**: HTTP transports serve session requests without verifying the authenticated principal.
  * **Affected Ranges**: `introduced: 0`, `fixed: 1.27.2`.
  * **Contradictory Metadata**: None. Both report fixed in 1.27.2.
  * **Withdrawn**: No.
* **Issue 3 (CVE-2026-59950)**:
  * **Aliases**: `GHSA-vj7q-gjh5-988w`, `PYSEC-2026-3483`.
  * **Summary**: WebSocket server transport does not enforce Host/Origin validation (Cross-Site WebSocket Hijacking).
  * **Affected Ranges**: `introduced: 0`, `fixed: 1.28.1`.
  * **Contradictory Metadata**: None. Both report fixed in 1.28.1.
  * **Withdrawn**: No.

### 2.4 nltk 3.10.0 (35 matches, 20 distinct issues)

Fifteen issues have dual GHSA and PYSEC records; five issues (`GHSA-5gh2-94qg-qppq`, `GHSA-6hwm-xvph-95vm`, `GHSA-ff5c-cp5c-9wjf`, `GHSA-qx2g-xrx7-vfh8`, `GHSA-vp2x-qp44-57v7`) exist in GHSA only.

1. **CVE-2026-79674** (`GHSA-3gq4-3j92-5w49`, `PYSEC-2026-3736`): Corpus Reader Sandbox Bypass. Fixed in `3.10.3`.
2. **CVE-2026-62383** (`GHSA-3hhw-38pf-pxj6`, `PYSEC-2026-3726`): Symlink arbitrary file read in `IPIPANCorpusReader`. Fixed in `3.10.2`.
3. **CVE-2026-71513** (`GHSA-5gh2-94qg-qppq`): `AllowlistUnpickler` dotted-name validation bypass leading to code execution. Fixed in `3.10.3`.
4. **CVE-2026-78680** (`GHSA-6hwm-xvph-95vm`): Uncontrolled search path when invoking Graphviz `dot` binary. Fixed in `3.10.3`.
5. **CVE-2026-78682** (`GHSA-6ww7-3frv-cqxh`, `PYSEC-2026-3733`): `pathsec` SSRF bypass when proxy configured. Fixed in `3.10.3`.
6. **CVE-2026-81726** (`GHSA-8mgp-746c-j5xp`, `PYSEC-2026-3740`): Model artifact APIs bypass `pathsec` outside root. Fixed in `3.10.3`.
7. **CVE-2026-81725** (`GHSA-8mpw-7fpc-4gqj`, `PYSEC-2026-3752`): `Pl196xCorpusReader` ReDoS on malformed TEI blocks. Fixed in `3.10.3`.
8. **CVE-2026-78681** (`GHSA-97qj-x29f-37w7`, `PYSEC-2026-3748`): Entity expansion DoS in raw `ElementTree` parses. Fixed in `3.10.3`.
9. **CVE-2026-71514** (`GHSA-cv22-g7mw-8v73`, `PYSEC-2026-3790`): `CrubadanCorpusReader` path traversal arbitrary file read. Fixed in `3.10.3`.
10. **CVE-2026-81724** (`GHSA-cw6x-m8jw-qmrh`, `PYSEC-2026-3739`): Uncontrolled recursion in `FeatStructReader` DoS. Fixed in `3.10.3`.
11. **CVE-2026-81727** (`GHSA-f794-5jv7-7672`, `PYSEC-2026-3741`): `Downloader.download` follows hardlinks outside root. Fixed in `3.10.3`.
12. **CVE-2026-62384** (`GHSA-f833-7jw8-xwrv`, `PYSEC-2026-3789`): Symlink sandbox bypass in `FramenetCorpusReader`. Fixed in `3.10.2`.
13. **CVE-2026-12876** (`GHSA-ff5c-cp5c-9wjf`): Resource consumption in `RecursiveDescentParser`. Fixed in `3.10.3`.
14. **CVE-2026-79675** (`GHSA-m4rf-3fr8-xwx3`, `PYSEC-2026-3749`): JVM argument injection in Stanford wrappers. Fixed in `3.10.3`.
15. **CVE-2026-79676** (`GHSA-p4rw-rvv2-7xwr`, `PYSEC-2026-3737`): Corpus readers follow symlinks outside root. Fixed in `3.10.3`.
16. **CVE-2026-72818** (`GHSA-qx2g-xrx7-vfh8`): `TweetTokenizer` catastrophic regex backtracking DoS. Fixed in `3.10.1`.
17. **CVE-2026-81723** (`GHSA-vp2x-qp44-57v7`): Quadratic CPU exhaustion in `XMLCorpusView._read_xml_fragment()`. Fixed in `3.10.3`.
18. **CVE-2026-80206** (`GHSA-w3v8-gmh9-3wv7`, `PYSEC-2026-3751`): ReDoS in `nltk.tgrep`. Fixed in `3.10.3`.
19. **CVE-2026-81722** (`GHSA-ww6m-cw3f-q94g`, `PYSEC-2026-3738`): Quadratic time DoS in `PorterStemmer` on long runs of 'y'. Fixed in `3.10.3`.
20. **CVE-2026-79657** (`GHSA-x99w-6fgc-pmfw`, `PYSEC-2026-3735`): Allowlisted pickle loaders permit code execution. Fixed in `3.10.3`.

* **Withdrawn**: None. All 35 records active.

### 2.5 pillow 10.4.0 (34 matches, 17 distinct issues)

Each of the 17 distinct issues has one `GHSA-*` and one `PYSEC-*` record (17 pairs = 34 records).

1. **CVE-2026-55379** (`GHSA-45hq-cxwh-f6vc`, `PYSEC-2026-2255`): `BdfFontFile` decompression bomb bypass. Fixed in `12.3.0`.
2. **CVE-2026-55798** (`GHSA-4x4j-2g7c-83w6`, `PYSEC-2026-2257`): `WindowsViewer.get_command()` command injection via shell path. Fixed in `12.3.0`.
3. **CVE-2026-54060** (`GHSA-5x94-69rx-g8h2`, `PYSEC-2026-2254`): `FontFile.compile()` decompression bomb bypass. Fixed in `12.3.0`.
4. **CVE-2026-54058** (`GHSA-62p4-gmf7-7g93`, `PYSEC-2026-3493`): Out-of-bounds read via row stride on McIdas AREA mmap path. Fixed in `12.3.0`.
5. **CVE-2026-59199** (`GHSA-6r8x-57c9-28j4`, `PYSEC-2026-3451`): Heap out-of-bounds write in `Image.paste()` / `Image.crop()` via signed coordinate overflow. Fixed in `12.3.0`.
6. **CVE-2026-54059** (`GHSA-8v84-f9pq-wr9x`, `PYSEC-2026-2253`): `PcfFontFile._load_bitmaps()` decompression bomb bypass. Fixed in `12.3.0`.
7. **CVE-2026-59205** (`GHSA-9hw9-ch79-4vh6`, `PYSEC-2026-3453`): Heap out-of-bounds write in `ImageCmsTransform.apply()`. Fixed in `12.3.0`.
8. **CVE-2026-25990** (`GHSA-cfh3-3jmp-rvhc`, `PYSEC-2026-2249`): Out-of-bounds write when loading PSD images. Fixed in `12.1.1`.
9. **CVE-2026-59198** (`GHSA-fj7v-r99m-22gq`, `PYSEC-2026-3494`): TGA RLE encoder heap disclosure (~57 KB). Fixed in `12.3.0`.
10. **CVE-2026-59200** (`GHSA-jjj6-mw9f-p565`, `PYSEC-2026-3495`): Decompression bomb DoS in `PdfParser.PdfStream.decode()`. Fixed in `12.3.0`.
11. **CVE-2026-55380** (`GHSA-phj9-mv4w-65pm`, `PYSEC-2026-2256`): `GdImageFile._open()` decompression bomb bypass. Fixed in `12.3.0`.
12. **CVE-2026-42311** (`GHSA-pwv6-vv43-88gr`, `PYSEC-2026-2252`): Out-of-bounds write with invalid PSD tile extents (integer overflow). Fixed in `12.2.0`.
13. **CVE-2026-42310** (`GHSA-r73j-pqj5-w3x7`, `PYSEC-2026-2874`): PDF parsing trailer infinite loop DoS. Fixed in `12.2.0`.
14. **CVE-2026-59204** (`GHSA-vjc4-5qp5-m44j`, `PYSEC-2026-3496`): JPEG2000 tiled decode growing scratch buffer DoS. Fixed in `12.3.0`.
15. **CVE-2026-40192** (`GHSA-whj4-6x5x-4v2j`, `PYSEC-2026-2250`): FITS GZIP decompression bomb. Fixed in `12.2.0`.
16. **CVE-2026-42308** (`GHSA-wjx4-4jcj-g98j`, `PYSEC-2026-165`): Integer overflow when processing fonts. Fixed in `12.2.0`.
17. **CVE-2026-59197** (`GHSA-xj96-63gp-2gmr`, `PYSEC-2026-3454`): Heap out-of-bounds write in `ImageFilter.RankFilter` via `ImagingExpand` integer overflow. Fixed in `12.3.0`.

* **Withdrawn**: None.

### 2.6 torch 2.8.0 (8 matches, 8 distinct issues)

* **Issue 1 (CVE-2025-3001)**: `GHSA-qfhq-4f3w-5fph`, `PYSEC-2025-195`. Memory corruption in `torch.lstm_cell`. Fixed in `2.10.0`.
* **Issue 2 (CVE-2025-3000)**: `GHSA-rrmf-rvhw-rf47`, `PYSEC-2025-194`. Memory corruption in `torch.jit.script`. Fixed in `2.13.0`.
* **Issue 3 (CVE-2025-2999)**: `GHSA-vgrw-7cvw-pwgx`, `PYSEC-2025-193`. Memory corruption in `unpack_sequence`. Fixed in `2.9.1`.
* **Issue 4 (CVE-2025-55551)**: `PYSEC-2025-203`. DoS in `torch.linalg.lu` slice operation. Fixed in `2.9.0`.
* **Issue 5 (CVE-2025-55552)**: `PYSEC-2025-204`. Unexpected behavior when `torch.rot90` and `torch.randn_like` are combined. Fixed in `2.9.0`.
* **Issue 6 (CVE-2025-55554)**: `PYSEC-2025-206`. Integer overflow in `torch.nan_to_num-.long()`. Fixed in `2.9.0`.
* **Issue 7 (CVE-2026-4538)**: `PYSEC-2026-139`. Deserialization in pt2 Loading Handler. Record has `last_affected: 2.10.0`, no fixed version (unmerged PR). Upstream unfixed.
* **Issue 8 (CVE-2026-24747)**: `PYSEC-2026-2286` (aliases `GHSA-63cw-57p8-fm3p`, `PYSEC-2026-1856`). Memory corruption / arbitrary code execution in `weights_only` unpickler via crafted `.pth` file in `torch.load(..., weights_only=True)`. Fixed in `2.10.0`.

* **Contradictory Metadata**: Four issues exist in PYSEC without a matching GHSA record in the query batch (`PYSEC-2025-203`, `PYSEC-2025-204`, `PYSEC-2025-206`, `PYSEC-2026-139`). `PYSEC-2026-2286` references `GHSA-63cw-57p8-fm3p`, which was not returned directly in the query.
* **Withdrawn**: None.

### 2.7 transformers 4.57.6 (8 matches, 5 distinct issues)

* **Issue 1 (CVE-2026-4372)**: `GHSA-29pf-2h5f-8g72`, `PYSEC-2026-2289`. RCE via `_attn_implementation_internal` repo ID in `config.json` during `AutoModelForCausalLM.from_pretrained()`. Fixed in `5.3.0`.
* **Issue 2 (CVE-2026-1839)**: `GHSA-69w3-r845-3855`, `PYSEC-2026-2288`. Arbitrary code execution in `Trainer` class via training arguments.
  * *Contradictory Metadata*: GHSA reports `fixed: 5.0.0rc3`; PYSEC reports `fixed: 5.0.0`.
* **Issue 3 (CVE-2026-5241)**: `GHSA-fgcw-684q-jj6r`, `PYSEC-2026-2290`. Arbitrary code execution during LightGlue model loading.
  * *Contradictory Metadata*: GHSA reports `fixed: 5.5.0`; PYSEC reports `last_affected: 5.2.0` with no fixed event.
* **Issue 4 (CVE-2026-9856)**: `GHSA-xrqw-3rrv-vx5w` (GHSA only). Path traversal in `save_pretrained` via chat template names. Fixed in `5.10.0`.
* **Issue 5 (CVE-2025-14929)**: `PYSEC-2025-217` (PYSEC only). Deserialization in X-CLIP checkpoint conversion script. Reports `last_affected: 5.0.0-rc0`. Upstream unfixed.

* **Withdrawn**: None.

---

## 3. First-Party Call Sites and Runtime Reachability

AST inspection across the entire repository confirms first-party imports and call boundaries:

```
Pillow (PIL):      16 import sites
mcp:               22 import sites
torch:              1 import site (whisper_runner.py:147)
whisperx:           2 import sites (whisper_runner.py:102, 294)
cryptography:       0 import sites
lightning:          0 import sites
nltk:               0 import sites
transformers:       0 import sites
```

### 3.1 Model Context Protocol (MCP)

* **Codebase Call Sites**: `uoink_mcp.py` imports `mcp.server.fastmcp.FastMCP` and `mcp.types`. At line 1290, execution explicitly invokes:
  ```python
  mcp.run(transport="stdio")
  ```
* **Transport Distinction**:
  * Uoink runs MCP exclusively over standard input/output (`stdio`).
  * CVE-2026-52870 affects experimental task handlers (`server.task`), which Uoink does not register or invoke.
  * CVE-2026-52869 affects HTTP/SSE transport session authentication. Uoink does not run an HTTP MCP server.
  * CVE-2026-59950 affects WebSocket server Host/Origin header validation. Uoink does not start an MCP WebSocket server.
* **Verdict**: None of the three MCP vulnerabilities are reachable in Uoink's stdio deployment. Upgrading to 1.28.1 is feasible but requires validating the Phase 5 SDK stream wrapping (`_SdkSettlementStream` in `uoink_mcp.py`).

### 3.2 Cryptography and PKCS#7 Functions

* **Codebase Call Sites**: Zero first-party imports of `cryptography` exist. Uoink never calls `pkcs7_decrypt_der`, `pkcs7_decrypt_pem`, or `pkcs7_decrypt_smime`.
* **Transitive Call Sites**:
  * `keyring` (25.7.0) on Windows uses `win32ctypes` to invoke the native Windows Credential Manager (`Advapi32.dll` / `CredReadW` / `CredWriteW`). It does not use PKCS#7.
  * `PyJWT` (2.13.0) uses HMAC/RSA/ECDSA signatures for JWT tokens; it does not decrypt PKCS#7 `EnvelopedData`.
  * `aiohttp`, `httpx`, and `urllib3` use TLS X.509 certificate validation, not S/MIME or CMS message decryption.
* **Verdict**: CVE-2026-69247 is unreachable in Uoink. Upgrading to `cryptography==50.0.1` is completely safe and satisfies all transitive constraints (`pyopenssl<51,>=49.0.0`).

### 3.3 Pillow (PIL) and Image Parsing

* **Codebase Call Sites**:
  * `images.py:195`: `_write_thumbnail` calls `Image.open(image_path)` on image files saved by `persist_image` (web page scrapes, user clipboards, and file drops). It converts to RGB, resizes with Lanczos, and encodes JPEG.
  * `server.py:6320`: `_encode_screenshot_b64` calls `Image.open(path)` to compress and base64-encode screenshots for the paste-corpus feature.
  * `server.py:9412`: `_ahash_file` calls `Image.open(path)` to compute average perceptual hashes for screenshot frame deduplication.
  * `uoink_tray.py:188`: `_load_base_glyph` loads `assets/logo-mark-color.png`.
  * Build-time tools: `generate_icon.py` and `generate_bitmaps.py`.
* **Reachability Analysis**:
  * Pillow's `Image.open` automatically inspects magic bytes and dispatches to the corresponding image format parser regardless of file extension.
  * An attacker who provides a crafted image via web clipping, paste, or local import directly exercises Pillow's format decoders.
  * Specifically reachable:
    * CVE-2026-25990 and CVE-2026-42311: PSD image parser out-of-bounds writes and integer overflows.
    * CVE-2026-54058: McIdas AREA row stride out-of-bounds read.
    * CVE-2026-59204: JPEG2000 tiled decode memory exhaustion DoS.
    * CVE-2026-59199: `Image.paste()` / `Image.crop()` signed coordinate heap out-of-bounds write.
  * Not reachable: `WindowsViewer.get_command()` (CVE-2026-55798; Uoink never calls `Image.show()`), font loaders (BDF, PCF, TTF; Uoink does not parse external fonts), PDF parser (Uoink does not pass PDFs to Pillow).
* **Verdict**: Pillow image parsing vulnerabilities are **directly reachable** on untrusted inputs. Updating Pillow from 10.4.0 to 12.3.0 is the single most important fix in this triage.

### 3.4 Checkpoint Loading and WhisperX Models

WhisperX, PyTorch, PyTorch Lightning, and Transformers operate across three distinct execution paths in `whisper_runner.py`:

```
1. Audio Transcription:
   whisperx.load_model(model_size, ...) -> faster-whisper / ctranslate2 (model.bin)
   [No PyTorch unpickling, no Transformers CausalLM]

2. Phoneme Alignment:
   whisperx.load_align_model(language_code, ...) -> Wav2Vec2 alignment model
   [Reads bundled torchaudio / huggingface wav2vec2 weights]

3. Speaker Diarization:
   whisperx.DiarizationPipeline(model_name="pyannote/speaker-diarization-community-1", ...)
   -> pyannote.audio -> LightningModule.load_from_checkpoint / torch.load
```

* **Whisper Audio Transcription**:
  * Uses `faster-whisper` and `ctranslate2`. Weights are stored as CTranslate2 native binary files (`model.bin`), not Python pickle or PyTorch `.pth` files.
  * Pinned to fixed model names: `tiny`, `base`, `small`, `medium`, `large`, `large-v3-turbo` (`whisper_runner.py:63-71`). Arbitrary model names from users are rejected by `normalize_model`.
  * Does not invoke PyTorch checkpoint unpicklers.
* **Speaker Diarization and Checkpoint Loading**:
  * `whisperx.DiarizationPipeline` invokes `pyannote.audio`, which loads model weights using PyTorch Lightning's `LightningModule.load_from_checkpoint` and PyTorch's `torch.load(..., weights_only=True)`.
  * **Reachability of Lightning CVE-2026-58659 and Torch CVE-2026-24747**:
    * Both vulnerabilities exploit deserialization in checkpoint loaders. Lightning's flaw bypasses `weights_only=True` by importing and executing hyperparameter class instantiators. Torch's flaw exploits a memory corruption bug in the `weights_only` unpickler itself.
    * In Uoink, the model name is hardcoded to `DIARIZATION_MODEL = "pyannote/speaker-diarization-community-1"` (`whisper_runner.py:184`). Users cannot supply arbitrary model paths.
    * Model downloads require explicit user consent (`consent_given=True` in `whisper_runner.py:269`, verified in `transcribe_audio` at line 306).
    * If local storage in `%LOCALAPPDATA%\Uoink\diarization_models` is modified by an attacker on the same machine, or if the Hugging Face repository were compromised, `load_from_checkpoint` would execute the payload upon user-initiated diarization.
    * Local file status does not guarantee safety. However, the path is gated behind user consent and hardcoded repository targets.
* **Transformers Reachability**:
  * First-party imports: Zero.
  * Uoink does not call `AutoModelForCausalLM.from_pretrained()` (CVE-2026-4372), does not invoke `Trainer` (CVE-2026-1839), does not use `LightGlue` (CVE-2026-5241), does not call `save_pretrained()` (CVE-2026-9856), and does not run X-CLIP conversion scripts (CVE-2025-14929).
  * WhisperX uses `transformers` for Wav2Vec2 feature extraction and tokenizer loading during alignment, not for CausalLM text generation.
* **NLTK Reachability**:
  * First-party imports: Zero.
  * WhisperX imports `nltk.tokenize.sent_tokenize` for segmenting transcript text before alignment.
  * None of the 20 NLTK vulnerabilities touch `sent_tokenize`. The flaws are located in corpus readers (`IPIPAN`, `Framenet`, `Crubadan`, `Pl196x`), corpus downloaders, Stanford Java wrappers, Graphviz process spawning, `FeatStructReader`, and `TweetTokenizer`.

---

## 4. Runtime Graph Analysis and Exact Repair Proposal

### 4.1 Dependency Constraint Matrix

Inspecting PyPI `Requires-Dist` metadata for the installed stack identifies two hard graph collisions:

```
whisperx 3.8.6:
  ├── torch~=2.8.0                       [MUST be >=2.8.0, <2.9.0]
  ├── torchaudio~=2.8.0                  [MUST be >=2.8.0, <2.9.0]
  ├── torchvision~=0.23.0                [MUST be >=0.23.0, <0.24.0]
  ├── torchcodec<0.8.0,>=0.6.0
  ├── huggingface-hub<1.0.0              [COLLISION with transformers 5.x]
  ├── nltk>=3.9.1                        [COMPATIBLE with nltk 3.10.3]
  └── transformers>=4.48.0

transformers 5.x:
  └── huggingface-hub>=1.3.0             [REQUIRES >=1.3.0 or >=1.5.0]
      ^^^ DIRECT CONFLICT with whisperx 3.8.6 requirement (huggingface-hub<1.0.0)

torch 2.8.x releases on PyPI:
  └── Only 2.8.0 exists                  [NO 2.8.1 or 2.8.2 patch release published]
      ^^^ PyTorch fixes for CVE-2025-3001, CVE-2026-24747 require torch>=2.10.0
      ^^^ Upgrading torch to 2.10.0 violates whisperx 3.8.6 pin (torch~=2.8.0)
```

### 4.2 Distinguishing Feasible Patches from Untested Suggestions

| Package | Current Pin | Proposed Pin | Feasibility Classification | Rationale & Verification |
| :--- | :--- | :--- | :--- | :--- |
| **Pillow** | 10.4.0 | **12.3.0** | **Feasible Patched Version** | Resolves all 17 Pillow issues. Verified: `pillow-12.3.0-cp311-cp311-win_amd64.whl` exists on PyPI. `torchvision` (`>=5.3.0`), `pystray`, and `matplotlib` (`>=9`) permit 12.3.0. Updates `$PILLOW_VERSION` in `build.ps1` and `requirements-installer-lock.txt`. |
| **nltk** | 3.10.0 | **3.10.3** | **Feasible Safe Upgrade** | Resolves all 20 NLTK issues. Verified: `nltk 3.10.3` is pure Python, published on PyPI, and satisfies `whisperx` constraint `nltk>=3.9.1`. Zero API changes to `sent_tokenize`. |
| **cryptography** | 49.0.0 | **50.0.1** | **Feasible Safe Upgrade** | Resolves CVE-2026-69247. Verified: `cryptography-50.0.1-cp311-abi3-win_amd64.whl` exists on PyPI. Satisfies `pyopenssl` (`cryptography<51,>=49.0.0`) and `pyjwt`. |
| **mcp** | 1.27.1 | **1.28.1** | **Feasible Patch (Pending Test)** | Resolves all 3 MCP issues. Available on PyPI. However, `uoink_mcp.py` contains Phase 5 SDK stream hooks (`_SdkSettlementStream`). Must pass `tests/test_c01_mcp_stdio.py` and `tests/test_phase5_*.py` before lock update. |
| **lightning** | 2.6.5 | **2.6.5 (Retain)** | **Upstream Unfixed on PyPI** | `2022.6.15` does not exist on PyPI. Latest PyPI release remains 2.6.5. Upgrading to an imaginary version fails build; dismissing it is invalid. Retain 2.6.5 with consent gating. |
| **torch** | 2.8.0 | **2.8.0 (Retain)** | **Graph Constrained (Infeasible)** | Upgrading to 2.10.0+ breaks `whisperx 3.8.6 -> torch~=2.8.0`. No 2.8.x patch exists. Must retain 2.8.0 until WhisperX releases an updated version supporting torch 2.10+. |
| **transformers**| 4.57.6 | **4.57.6 (Retain)** | **Graph Constrained (Infeasible)** | Upgrading to 5.x breaks `whisperx 3.8.6 -> huggingface-hub<1.0.0`. Flaws in Trainer, LightGlue, and CausalLM are unreachable in Uoink. Retain 4.57.6. |

---

## 5. Prioritized Action Plan and Verification Test Plan

### 5.1 Prioritized Release Steps

1. **Priority 1 (Exploitable Release Exposure: Pillow)**:
   * Bump `$PILLOW_VERSION = '12.3.0'` in `build.ps1` (line 115).
   * Update `pillow==12.3.0` in `requirements-installer-lock.txt` (line 92).
   * This eliminates active heap corruption and out-of-bounds write risks on image decoding in `images.py` and `server.py`.
2. **Priority 2 (Clean Transitive Hardening: NLTK and Cryptography)**:
   * Update `nltk==3.10.3` and `cryptography==50.0.1` in `requirements-installer-lock.txt`.
   * Neither package has custom call sites in Uoink; both satisfy all peer constraints.
3. **Priority 3 (Controlled Protocol Bump: MCP)**:
   * Prepare a candidate lock with `mcp==1.28.1` and `$MCP_VERSION = '1.28.1'`.
   * Run the isolated Phase 5 SDK settlement test suite to confirm that `uoink_mcp.py` serializer hooks remain compatible with MCP 1.28.1 internals.
4. **Priority 4 (Documented Upstream Deferrals: Lightning, Torch, Transformers)**:
   * Do not alter `lightning==2.6.5`, `torch==2.8.0`, or `transformers==4.57.6`.
   * Record upstream-unfixed status for Lightning commit `d710d68`.
   * Record graph-blocked status for Torch and Transformers pending a WhisperX upstream release.

### 5.2 Required Offline Regression and Verification Suite

Before Astra integrates lockfile modifications into the installer tree, the following offline verification passes are required:

1. **Isolated Dependency Resolution and Lock Verification**:
   * Run `scripts/verify_installer_lock.py` against `requirements-installer-lock.txt` in the test environment to guarantee zero missing, unexpected, or drifted pins.
2. **Image Processing and Asset Generation Regression**:
   * Execute `python tests/test_image_capture.py`.
   * Execute `python tests/test_screenshots_picker_v324.py`.
   * Execute `python installer/generate_icon.py` and `python installer/generate_bitmaps.py` to confirm Pillow 12.3.0 generates the `.ico` and wizard `.bmp` assets cleanly without Lanczos/RGBA deprecation breaks.
3. **MCP Stdio Integration and Protocol Conformance**:
   * Execute `python tests/test_c01_mcp_stdio.py` (`python -P` stdio handshake verification).
   * Execute `python tests/test_phase5_az5d2.py`, `tests/test_phase5_az5h.py`, `tests/test_phase5_az5h2.py`, and `tests/test_phase5_sdk_original_route.py` to confirm that request admission, frame settlement, and error serialization operate cleanly.
4. **WhisperX Import and Runtime Device Probe**:
   * Execute the staged smoke probe from `build.ps1:692-693`:
     ```python
     import whisperx
     print("smoke: import whisperx OK")
     ```
   * Confirm that `_probe_whisperx()` in `whisper_runner.py` completes within the cold-boot splash retry budget on CPU and CUDA.
   * Verify `whisper_runner.is_model_downloaded` and `_runtime_device` without executing speaker diarization or model downloads.
5. **Installer Staging and Third-Party Notice Generation**:
   * Run `scripts/gen_third_party_notices.py` to ensure `pip-licenses` reads the updated metadata and outputs valid licenses for Pillow 12.3.0, NLTK 3.10.3, and Cryptography 50.0.1 without missing notice errors.

---

## 6. Handoff to Astra

* **Triage Complete**: Raw OSV matches (95) resolved to 55 distinct issues across 7 packages.
* **Document Created**: `docs/library/GEMINI-INSTALLER-ADVISORY-TRIAGE-2026-09-09.md`.
* **Zero Worktree Code / Lock Edits**: No modifications were made to `requirements-installer-lock.txt`, `build.ps1`, or production source files.
* **Ready for Independent Review**: Astra can inspect the dependency graph analysis, resolve candidate wheels in a disposable virtual environment, and generate the formal repair brief.
