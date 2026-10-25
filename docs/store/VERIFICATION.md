# Build and verification receipt

Prepared on 2026-10-24 in `feat/cws-ready`. No commits, pushes, ref changes,
account creation, uploads or submissions. Release version fields remain 3.11.0.

## Upload archive

- Path: `dist/uoink-extension-3.11.0-cws.zip`
- Size: **372,021 bytes** (363.30 KiB)
- Files: **45**, all from `extension/`, with the manifest at the archive root
- SHA-256: `9e7a3cd9985b095d76cceacc3467b246d54c5e8d466b5246a6534625fcfe04c8`
- Machine-readable receipt: `dist/uoink-extension-3.11.0-cws.contents.json`

Build with `python scripts/build_cws.py`. The script uses an explicit allowlist,
rejects unexpected or missing files and links, checks MV3/release version,
validates local references and store config, and fixes ZIP order and timestamps.
The reproducibility test builds twice and compares bytes. The receipt records
each file's size and hash. A future source/config change produces a new receipt.

The archive omits the source manifest key and `lib/mock-api.js`. Mock mode is
hard-disabled with `USE_MOCK_API = false`. No source maps, helper files, test
files, screenshots or development credentials are included. The source key
remains unchanged. `dist/` is ignored by Git.

```text
background.js
brand/fonts/bungee-OFL.txt
brand/fonts/bungee.woff
brand/fonts/inter-OFL.txt
brand/fonts/inter-italic.woff
brand/fonts/inter.woff
brand/fonts/jetbrains-mono-OFL.txt
brand/fonts/jetbrains-mono.woff
brand/tokens.css
content-reddit.js
content-x-article.js
content.js
icons/icon-128-dark.png
icons/icon-128-light.png
icons/icon-128.png
icons/icon-16-dark.png
icons/icon-16-light.png
icons/icon-16.png
icons/icon-32-dark.png
icons/icon-32-light.png
icons/icon-32.png
icons/icon-48-dark.png
icons/icon-48-light.png
icons/icon-48.png
icons/icon128.png
icons/icon16.png
icons/icon32.png
icons/icon48.png
lib/extract.js
lib/popup-captures.js
lib/store-links.js
lib/ui.js
lib/x-article.js
manifest.json
offscreen.html
offscreen.js
popup.html
popup.js
prompts.json
setup.html
setup.js
store-config.json
uoink-memory.css
uoink-memory.html
uoink-memory.js
```

## Checks completed

All Python verification used:
`E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/ig-native/Scripts/python.exe`.
Jobs ran at BelowNormal priority, one heavy job at a time. Pytest used
`-p no:cacheprovider` with:

```text
UOINK_URL=http://127.0.0.1:1
IG_FORBIDDEN_LIVE=C:\Users\hello\AppData\Local\Uoink\index.db
PYTHONPATH=E:\AI\projects\uoink\checkouts\Yoink-cws
PYTHONDONTWRITEBYTECODE=1
```

App-data, temporary files, output and the isolated test profile were redirected
under this worktree's `_scratch/cws`. Usage sharing was disabled. The verification
interpreter's existing guard also blocked the live database and helper port.

| Check | Result |
|---|---|
| Extension syntax and ESLint | Passed for every extension JS file, using the CI no-undef rules. |
| Origin, token and security tests | Passed: every `tests/test_sec_*.py`, tests referring to `PINNED_EXTENSION_ID` or `ALLOWED_ORIGINS`, DNS-rebinding, MCP-slug and security-findings tests. Log reports 1,470 passed executions; overlapping absolute/relative selections collected some tests twice. Four existing `datetime.utcnow` deprecation warnings. |
| Setup/splash and related tests | 80 passed, including both store-link states, missing helper, setup preferences, external links and SPA host patterns. |
| Final focused regression run | 144 passed after fixing the offscreen startup race and its asynchronous test synchronization. Includes CWS packaging/link tests, token pin tests and installer checks. |
| Additional integration checks | Sender pin, page-script, setup, SPA and Mac payload-layout checks passed. No native Mac build was attempted. |
| MCP inventory | Passed: 91 full tools, 35 core tools. |
| `ci.yml` static jobs | Passed locally: extension checks, JSON/version/log guards, CWS build, backend compilation, MCP inventory, generated agent-kit check, store-copy sync check and Bash syntax. Used the workflow's `bash -n` fallback because ShellCheck is unavailable. |
| Package negative tests | Unknown files, source maps, private-key filenames, enabled mock mode and version drift are rejected. Source key is preserved; repeated builds match. |
| Store setting boundary | Empty/configured URL states tested in actual setup/splash functions and generated README/website copy. Malformed IDs/URLs fail closed; store and developer token access work, suffix/path/port/query/userinfo origin variants fail. |
| Final documentation check | Five current-document reference tests passed. Local links, listing/manifest summary, screenshot dimensions, archive hashes and blank store config checked. `git diff --check` passed. |

Local logs and scripts are in ignored `_scratch/cws/`: `security.log`,
`setup.log`, `confirm-tests.log`, `static.log`, `browser-smoke.json`,
`browser-smoke.log`, `env.ps1`, `static.py` and `smoke.py`.

## Browser load test

Chrome for Testing **153.0.8010.12** loaded the extracted contents of the final
ZIP in a new profile under `_scratch/cws`. This tests the upload payload through
Chrome's extension loader; it is not a signed Web Store installation or a
Google review. The path-derived test ID is not a store ID.

The browser ran headless with sandboxing disabled for this disposable process
because the local Windows sandbox/GPU process failed to start. A closed proxy
at `127.0.0.1:1`, including loopback traffic, blocked all helper and outside
requests. No helper was started or contacted, and no real browser profile or
installed extension was modified. The test browser was closed afterward.

- MV3 service worker and offscreen document loaded from the archive.
- Setup showed **Uoink is offline**, Windows start instructions and a disabled
  capture button. The empty store URL kept the store-install notice hidden.
- Popup showed **Offline**, start instructions and disabled paste/capture controls.
- **Zero JavaScript exceptions, console errors or console warnings.**
- Five expected network-error entries reported `ERR_PROXY_CONNECTION_FAILED`
  for blocked health/token/recent requests. This is not a claim that the browser
  has no network-error entries while the helper is absent.

The test exposed an offscreen-document startup race. Callers now share the
lookup and creation promise and wait until the document is ready. The final
browser run and regression test passed after that fix.

Successful capture with a store identity remains a release check after Ryan
creates the draft and includes its ID in the helper. This pass did not run the
public installer, use Ryan's library, or invent replacement store screenshots.
