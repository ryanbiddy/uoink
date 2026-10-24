# Article extraction UX2 verification

The initial implementation below was committed as `50bd21a`, on `feat/article-extract` from base `90349a3f6b3431f52908968674319bc60f67634f`, with zero new runtime dependencies. This initial verification record is retained. The [repair results](#repair-of-50bd21a) at the end describe the review fixes committed as `333cec9`.

Installed Windows users previously received the regex `stdlib` path. The `.mcpb` inherits its installed runtime, and the Mac build recipe also omits Crawl4AI. The [original audit](article-extraction-ux2-audit.md) retains the packaging evidence and the rejected Trafilatura measurements, with the approved decision added above it.

The new `readability_stdlib` extractor, version `1`, adapts scoring and sibling selection from [Mozilla Readability 0.6.0](https://github.com/mozilla/readability/blob/0.6.0/Readability.js). It uses html.parser and accepts HTML already fetched through Uoink's existing public-URL and redirect checks. It cannot fetch, execute scripts or access browser state. The module is 19,754 bytes and the new Apache-2.0 notice is 11,606 bytes. Dependency locks and requirements are unchanged; an installer-size delta was not measured.

Successful articles carry the extractor version, fetch time, fetched URL, attempts and output truncation state. Author, publication date and site name come from JSON-LD, OpenGraph or meta tags, with visible byline/title fallbacks. Attribution appears in saved Markdown and the existing sidecar/metadata fields. Publication still uses `persist_page_yoink` and `Index.upsert_yoink`; the URL hash, folder naming, sidecar schema version and corpus.read/1 keys are unchanged. Redirects affect relative-link resolution, not source identity.

Fallback order is Readability adaptation, optional Crawl4AI, then legacy regex. Clear login/paywall pages and resource-limit failures stop immediately. A missing or short body cannot be rescued by regex returning navigation text. The JS shell fixture reaches regex last, returns `ok=false`, and retains both attempts in its provenance.

All seven pages below are small synthetic fixtures in `tests/fixtures/articles`. The before column was measured with the actual regex extractor from Git base `90349a3`, fed the same saved bytes through an in-memory HTTP response. No third-party articles or live page fetches were used.

| Fixture | Before | After |
|---|---|---|
| Noisy news | 800 Markdown characters; nav, ads and related text; no inline links or JSON-LD attribution | 549 characters; article body and heading retained, noise removed, absolute link retained, Mira Vale and 2026-10-20 recorded |
| Technical article | 772 characters; nav retained; code, table and links flattened | 865 characters; code indentation/fence, inline code, table, blockquote and safe links retained |
| List-heavy article | 813 characters; nav/related text and broken list markers | 775 characters; ordered, unordered and nested lists plus inline link; noise removed |
| Empty JS shell | 63 characters, incorrectly `ok=true` | Empty Markdown, `ok=false`, diagnostic identifies an empty JavaScript page |
| Paywall shell | 222 characters, incorrectly `ok=true` | Empty Markdown, `ok=false`, diagnostic identifies login/paywall |
| Login wall | 122 characters, incorrectly `ok=true` | Empty Markdown, `ok=false`, diagnostic identifies login/paywall |
| Meta attribution | 578 characters; reversed meta attribute order loses attribution; no inline link | 586 characters; Rowan Moss, publication timestamp, site name, OpenGraph title and link retained |

The successful fixtures record `readability_stdlib` version `1`. Paywall/login refusals record that engine too. The JS refusal records `stdlib` version `1` as the final attempt, following `readability_stdlib`. Tests verify that failed results publish neither files nor rows.

A 2 MiB synthetic page (2,097,152 bytes) took **0.237 seconds** in the final test run and **0.216 seconds** in the saved comparison run. It returned 99,998 Markdown characters and `output_truncated=true`. Limits are 8 MiB input, 40,000 elements, nesting depth 80, a cooperative 2-second processing deadline, 100,000 Markdown characters, 200 minimum body characters, and diagnostics of at most 240 characters. Tests cover input, element, depth, time and output limits, unsafe links, sibling joining, link density, long wall boilerplate and redirect identity.

Verification used `E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/ig-native/Scripts/python.exe` (CPython 3.14.6), BelowNormal priority, `PYTHONPATH` set to this worktree, `PYTHONDONTWRITEBYTECODE=1`, `UOINK_URL=http://127.0.0.1:1`, and `IG_FORBIDDEN_LIVE=C:/Users/hello/AppData/Local/Uoink/index.db`. `_scratch/run_article_checks.py` redirects profile, output, temp, log and app-data paths into this worktree and disables the real credential backend. The native guard denies external network and port 5179; an additional guard denies the protected app, corpus, keys and Chrome paths. Existing HTTP contract tests use synthetic local fixture servers, not the running helper.

The first broad collection exposed an old MCP SDK in ig-native. No shared environment was changed. Five already-required pins (mcp/mcp-types 2.3.0, httpx2/httpcore2 2.16.0 and truststore 0.10.5) were installed from uv's offline cache into `_scratch/sdk2-test-deps`; opentelemetry-api 1.44.0 was copied from the existing SDK2 checkout's test venv. This is a test-only import overlay, not a shipping dependency change. No dependency downloads were made in this implementation pass.

| Command/check | Result |
|---|---|
| `python -B _scratch/run_article_checks.py -q` with the broad file set below | 1,050 passed, 4 skipped in 92.46 seconds |
| `python -B _scratch/run_article_checks.py -q -s tests/test_page_extractor_articles.py tests/test_page_url_validation.py tests/test_notice_integration.py tests/test_installer_dependency_lock.py tests/test_reddit_extractor.py` after final shell/formatting changes | 56 passed in 1.10 seconds, including all 30 article tests |
| `python -B _scratch/article_fixture_report.py` | Saved before/after evidence and timing in `_scratch/article-fixture-comparison.json` |
| `python -B _scratch/static_article_checks.py` | All ci.yml static jobs passed; backend bytecode confined to `_scratch/static` |
| `python -B scripts/check_mcp_inventory.py` | 91 full tools, 35 core; docs, bundle, receipt and metadata agree |
| `python -B scripts/build_agent_kit.py --check` | Generated skills, client tables and version agree |
| Extension `node --check`, cached ESLint 8.57.1 with ci.yml flags | 13 JavaScript files passed; no network install |
| JSON validation, manifest/VERSION comparison, no-noisy-log guard, `bash -n scripts/verify-launch-readiness.sh` | Passed |
| Notice generation/integration, installer lock and Mac lock tests | Passed; adapted attribution survives generation and committed blocks match |
| `git diff --check` | Passed |

Both pytest commands use `-p no:cacheprovider` through the launcher. The broad set was:

```text
tests/test_page_extractor_articles.py tests/test_page_url_validation.py
tests/test_corpus_contract_v1.py tests/test_sec_public_surfaces.py
tests/test_v2a_universal_capture.py tests/test_phase0_registry_capture.py
tests/test_notes_capture.py tests/test_image_capture.py tests/test_u15_x_capture.py
tests/test_unique_capture_folders.py tests/test_cat_p1_routing_feedback.py
tests/test_cat_p2_taxonomy.py tests/test_v333_live_fixes.py tests/test_reddit_extractor.py
tests/test_notice_integration.py tests/test_installer_dependency_lock.py
tests/test_mac_posix_locks.py tests/test_runtime_setuptools_notices.py
tests/test_bundled_font_notices.py tests/test_sec_ssrf.py
```

The four skips are POSIX fcntl contention/recovery cases on Windows. Warnings are existing datetime.utcnow deprecations. Logs are `_scratch/article-focused-tests.log`, `_scratch/article-final-tests.log` and `_scratch/article-static-checks.log`.

Files changed or added:

- `article_extractor.py`, `page_extractor.py`.
- `build.ps1`, `installer/uoink.iss`, `scripts/mac/payload.json` to ship and compile the new module and notice.
- `THIRD-PARTY-NOTICES.md`, `scripts/gen_third_party_notices.py`, `third-party-notices/README.md`, and `third-party-notices/mozilla-readability-APACHE-2.0.txt`.
- `tests/test_page_extractor_articles.py` and the seven `tests/fixtures/articles/*.html` files.
- `tests/test_sec_ssrf.py`, `tests/test_cat_p1_routing_feedback.py`, `tests/test_v333_live_fixes.py` to place existing test doubles at the new fetch/extraction boundary.
- The original audit report with its decision line, and this verification report. Disposable verification tools and output remain under ignored `_scratch`.

Remaining limits: this is a heuristic adaptation, not Mozilla's complete browser DOM implementation. Very short articles, unusual markup, non-English wall prompts and complex tables may need future fixtures; tables are limited to 20 columns and disclose truncation. Static success does not render JavaScript or capture a screenshot. Crawl4AI is absent from packaged builds and its fallback was tested with injected results, not a live browser. Its existing browser/network behavior was not expanded in this pass. The full WSL suite and installer/Mac builds remain for the orchestrator.

## Repair of 50bd21a

The repair runs wall and JavaScript checks on selected content after removing header, navigation, footer, aside, form and noscript chrome. Prompt coverage and distinct sentences distinguish a wall from a passing mention; repeated boilerplate cannot hide a wall. JavaScript prompt detection has no page-length ceiling. Script-backed loaders and repeated short sentences are rejected, including through fallback extraction.

The first safe document `base href` resolves relative links. Invalid schemes and credentials, including an empty username, fall back to the fetched URL. Byline hints match class/id token boundaries, skip html/body/main/article containers, and choose the shortest matching text. JSON-LD handling is unchanged.

Titled prose briefs of at least 80 characters can publish with `article_status=short_article` and the diagnostic `short article`. Extraction limits now try optional Crawl4AI and then regex. The fetch boundary still refuses responses over 8 MiB before any extractor runs. Source identity, publication, corpus.read/1 keys, product versions, packaging and dependency files are unchanged. No packages were installed; added runtime dependency size is zero. The original audit and its Trafilatura decision remain unchanged.

| Regression | Before repair | After repair |
|---|---|---|
| 364-character article with header sign-in link | Rejected as login/paywall | Article retained; header removed |
| 283-character article mentioning `subscribe to read` | Rejected as login/paywall | Article retained |
| Real article with standard noscript warning | Rejected as empty JavaScript page | Article retained; warning removed |
| 1,519-character repeated JavaScript prompt | Published as an article | Refused as empty JavaScript page |
| 399-character repeated loader | Published as an article | Refused as empty JavaScript page |
| CDN `base href` and relative `photo.html` | Link used the fetch directory | Link uses the CDN base; unsafe links remain dropped |
| `body.author-jane` before a byline | Article text became author | `Jane Doe` |
| `div.authority` before `span.author` | `City Desk` became author | `Jane Doe` |
| 2,404-character div article with header password form | Rejected as login/paywall | Article retained; form removed |
| 125-character titled paragraph | Rejected as too short | Published and labeled `short article` |
| 90 nested divs | Extraction limit ended capture | Crawl4AI or regex recovers the article; failed attempt recorded |

Tests also cover 93- and 199-character briefs, a deep brief, long login/paywall boilerplate, JavaScript prompts without punctuation, a 3,039-character shell, fallback loaders, invalid bases, and the terminal fetch cap. All seven original saved HTML fixtures still pass.

Verification used the same ig-native interpreter, isolated scratch profile, forbidden-live guard and offline test overlay described above. Every Python run used BelowNormal priority, `UOINK_URL=http://127.0.0.1:1`, `IG_FORBIDDEN_LIVE`, this worktree's `PYTHONPATH`, and `PYTHONDONTWRITEBYTECODE=1`. The pytest launcher adds `-p no:cacheprovider`. No live pages or external network were used.

| Command | Result |
|---|---|
| `python -B _scratch/run_article_checks.py -q -s` with the broad file set listed above | 1,083 passed, 4 skipped in 79.25 seconds |
| `python -B _scratch/run_article_checks.py -q tests/test_dashboard_capture_outcomes.py` | 12 passed in 1.11 seconds |
| `python -B _scratch/static_article_checks.py` | All ci.yml static checks passed, including MCP inventory, agent kit, Python compile, extension syntax/lint, JSON/version checks and Bash syntax |
| Notice generation/integration and Windows/Mac lock tests in the broad run | Passed |
| `git diff --check` | Passed |

The 2 MiB synthetic page took **0.315 seconds** and returned 99,998 Markdown characters with truncation recorded. The four skips are Windows-inapplicable POSIX lock tests. Warnings are existing `datetime.utcnow` deprecations. Logs are `_scratch/article-repair-verification.log`, `_scratch/article-repair-dashboard.log` and `_scratch/article-repair-static.log`.

Changed files: `article_extractor.py`, `page_extractor.py`, `tests/test_page_extractor_articles.py`, and this report. The repair was committed as `333cec9`. Known gap: a script-backed page that repeats an unpunctuated loader phrase (for example "Loading the reader") can still publish.

Open risks: shell detection remains a language-sensitive heuristic. The regex fallback has weaker content selection when the main extractor reaches a limit. Crawl4AI recovery was tested with injected results; no live browser was run. The full WSL suite and builds remain for the orchestrator.
