# QA smoke: one command before a release

`scripts/qa_smoke.py` checks the main paths a person uses, against a made-up
library, in a few minutes. It is dev only: nothing here ships in the installer
or the extension zip, and it is not part of required CI.

```powershell
# once per machine
cd tests\e2e
npm ci
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\..\..\_scratch\ms-playwright"
npx playwright install --no-shell chromium
cd ..\..

# every release
.\scripts\qa_smoke.ps1            # Windows
scripts/qa_smoke.sh               # macOS, Linux, Git Bash
python scripts/qa_smoke.py        # anywhere (set PLAYWRIGHT_BROWSERS_PATH yourself)
```

## What it does

1. Seeds an isolated profile with no network (`tests/e2e/qa_seed.py`):
   about 40 made-up items across YouTube, podcasts, X posts, Reddit and web
   pages, with and without transcripts, long titles, several shelves and some
   Uncategorized. It also seeds an empty library and a 1,000-item library.
2. Starts the helper with no window on a free port between 18150 and 18199
   (never 5179) through `tests/e2e/qa_helper.py`. That launcher raises the
   token and search rate limits, turns off desktop balloons, and lets the
   helper fetch only the local fixture page. Every other web fetch fails.
3. Runs the suites:
   - **api**: health, list, search with timestamp, item details, corpus read,
     MCP HTTP tool list (99) and a `search_library` call.
   - **cli**: `uoink status`, `tools` (99/36/9/7 for full/core/search/research),
     `recent`, `search`, `get`.
   - **dashboard**: loads with no console errors, lists every item and kind,
     search finds a spoken phrase and opens the reader at its timestamp, items
     open with their transcript, a settings switch saves and survives a reload,
     the health drawer and Activity render, the empty library, and a 1,000-item
     library loaded in full. Each runs at 390px and 1280px, light and dark.
   - **a11y**: Playwright aria snapshots for unnamed controls, visible focus
     while tabbing, and dialogs that keep focus inside and close with Escape.
   - **extension**: a copy of `extension/` pointed at the test port loads in
     Chromium's new headless mode. Setup says Connected, the popup says
     Running, and "Uoink this page" saves a local fixture page that then shows
     in the Library. The shipped extension files are never edited.
4. Stops the helper, prints a pass/fail table and writes `index.html`, a
   contact sheet of every screenshot, in the run folder
   (`_scratch/qa-smoke/<time>/` unless `--run-dir` says otherwise).

The exit code is 0 only on `RESULT: PASS`.

## Options

| Option | What it does |
|---|---|
| `--suites api,dashboard,extension` | Run only some suites (`api` includes the CLI checks). |
| `--variants light-1280,dark-390` | Run only some dashboard sizes and themes. |
| `--port 18150` | Use this port for the helper. 5179 is refused. |
| `--run-dir PATH` | Where logs, reports and screenshots go. |
| `--break search-500` | The search API answers 500. The run must fail. |
| `--break search-hidden` | The dashboard search box is hidden with CSS. The run must fail. |
| `--headed` | Show the extension browser window (`UOINK_E2E_HEADED=1`). |

Without `--headed`, nothing opens on screen: the helper, Python children and
Chromium all run hidden.

## Known issues

Problems the suite has already found and reported are listed in
`tests/e2e/known-issues.json`. A matching problem shows in the table's
`known` column and on the contact sheet instead of failing the run. Anything
new fails. When a known issue is fixed, delete its entry so the check guards it
again.

## Running a suite by hand

The Playwright specs read `UOINK_QA_BASE_URL`, `UOINK_QA_PROFILE`,
`UOINK_QA_RUN_DIR` and `UOINK_QA_STATE`, which `qa_smoke.py` sets. The
extension specs skip unless `UOINK_E2E_EXTENSION=headless` or
`UOINK_E2E_HEADED=1` is set.
