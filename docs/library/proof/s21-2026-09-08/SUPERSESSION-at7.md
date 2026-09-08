# Supersession record: S21 run at7 replaces the browser-observed runs at6 (AT6) and the C21 pill run

Written by Fable, 2026-09-08 ~15:30 PDT, for Astra's AS-7 C21 evidence requirements.

Run at7 executed Astra's launcher `tests/library_work_astra/test_phase3_s21.py` unchanged on
candidate `1d9e438` through `tests/library_work_astra/s21_run_record.py`, which retains:

- `executed-launcher-at7-1d9e438.py`: the launcher bytes as executed (raw sha256
  `d17a84c6…`, equal to the hash the receipt records under `input_hashes`);
- `run-record-at7-candidate-1d9e438.json`: exact command, cwd, interpreter, environment,
  start/finish (UTC), wall time, process exit status `0`, the artifact manifest with
  per-file hash comparison against the receipt (all match), and the evidence database hash;
- `receipt-at7-candidate-1d9e438.json`: the launcher's own receipt, verbatim (result
  `AUTOMATED PASS`, 0 model calls, no forbidden attempts, clip 12.5-21.75, unfiled, the
  item's classification `waiting_for_client`, feed `http://127.0.0.1:59403/feed.xml`,
  helper `http://127.0.0.1:59404`);
- `evidence-at7-candidate-1d9e438.db`: the retained database (hash equals the receipt's
  `evidence_sha256`);
- `artifacts-at7-candidate-1d9e438/`: every file the receipt hashes (fixture transcript,
  helper server log, source instance JSON, podcast sidecar and Markdown, retained
  `.media-inputs` JSON, generated taxonomy JSON, the evidence database) plus
  `logs/stdout-at7.log` and `logs/stderr-at7.log`;
- `browser-observation-at7.json` and the three screenshots taken during the same
  process's hold (`dashboard-sources-waiting-for-client-at7.jpg`,
  `dashboard-library-unfiled-at7.jpg`, `dashboard-item-detail-at7.jpg`): the feed port
  `59403` and dashboard port `59404` visible in the images equal the receipt's
  `feed_url`/`helper_url`, binding the browser run to this receipt and database.

Superseded for the C21 evidence requirements: the AT6 receipt/database pair (feed port
`60407`, whose browser images came from a different held run on port `64703`) and the
first C21 pill image (feed `49557`, taken on the S20 overlay without a retained receipt).
Those files remain in this directory as history and keep their AS-6 credit for what they
showed; AS-7's selectors (`receipt-at6-candidate-1830b7a.json`, ports `64703`/`49557`)
point at the superseded evidence and are for Astra to re-select against run at7
(`receipt-at7-candidate-1d9e438.json`, port `59403`).

Scope note (AS-7): this run replaces only the HTTP listener-free S21 controlled capture
with a held process; process termination/relaunch remains C22 (installed helper, Ryan).
