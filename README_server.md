# Local Server (`server.py`)

The browser extension talks to this server at `http://127.0.0.1:5179`.
It runs the same yt-dlp + ffmpeg pipeline as the GUI, but exposed as JSON
endpoints with CORS allowed for youtube.com.

## Dependencies

Pure Python stdlib — **no fastapi/flask/uvicorn install required**. Windows
desktop notifications use the built-in PowerShell/NotifyIcon path; no optional
toast package is required.

You also still need the same external tools as the GUI:

```
pip install yt-dlp
winget install Gyan.FFmpeg
```

## Running

Double-click **`start_server.bat`**, or:

```
pythonw server.py
```

(Use `python server.py` instead if you want logs streaming to a console.)

PowerShell equivalent:

```
.\start_server.ps1
```

Verify it's alive at `http://127.0.0.1:5179/ping`. A live helper returns HTTP
200 with `"ok": true`; the full response shape is documented below.

Logs are written to `server.log` next to `server.py`.

## Command line

The repository includes a small `uoink` wrapper. On Windows, replace `uoink`
below with `.\uoink.cmd`; on macOS or Linux, use `./uoink`.

```text
uoink doctor
uoink rebuild-index
uoink search <query>
uoink clips <query>
```

`doctor` prints helper health, schema-migration state, and the existing
diagnostics as JSON. `rebuild-index` runs the existing on-disk rebuild and
accepts an optional corpus root. `search` and `clips` send the query to the
running helper's authenticated HTTP tool registry and print its JSON response.

## Install the Windows watchdog

From the repository or installed Uoink directory, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-watchdog.ps1
```

The script creates or updates the current user's `Uoink Helper` Scheduled Task.
It starts the helper at logon and, if the process fails, retries three times at
one-minute intervals. Re-run the same command after moving the install folder.
Use `-WhatIf` to inspect the intended registration without changing the task.

Desktop notifications default on. Turn off **Show desktop notifications** in
Dashboard → Settings → Local app to keep background work invisible. Suppressed
events remain in Activity, and Uoink suppresses balloons automatically while a
foreground window covers its monitor. The authenticated settings equivalent is
`POST /settings` with `{"notifications_enabled": false}`; no restart is needed.

## Endpoints

### `GET /ping`

Values vary with the installed version, selected Whisper model, downloaded
models, output-root recovery, and corpus state. The response shape is:

```json
{
  "ok": true,
  "version": "<current version>",
  "migration_version": 25,
  "migration_pending": false,
  "last_successful_tick_at": "2026-09-04T16:30:00Z",
  "heartbeat": {
    "last_tick_completed_at": "2026-09-04T16:30:00Z",
    "last_successful_tick_at": "2026-09-04T16:30:00Z",
    "last_successful_poll_at": "2026-09-04T16:29:58Z",
    "last_failed_poll_at": null,
    "last_poll_error": null,
    "last_ingest_completed_at": null,
    "last_tick": {"ok": true, "polls": 1, "failed_polls": 0},
    "counts": {"ticks": 12, "polls_ok": 3, "polls_failed": 0, "ingests": 0},
    "tick_interval_sec": 30,
    "freshness": {"state": "fresh", "age_sec": 4.0, "stale_after_sec": 300}
  },
  "whisperx_available": false,
  "whisper_model": "base",
  "whisperx_model_loaded": false,
  "index_recovering": false,
  "output_root_fallback": false,
  "path_integrity": {
    "ok": true,
    "checked": 0,
    "missing": 0
  }
}
```

`path_integrity` always contains `ok`, `checked`, and `missing`. When indexed
files are missing it also contains a human-readable `hint`; if the index scan
itself fails it instead contains an `error` string.

`migration_version` is the newest schema migration opened by this helper.
`migration_pending` becomes `true` if newer migration files appear while it is
running. `last_successful_tick_at` is an RFC 3339 UTC timestamp; it is `null`
until the background source scheduler completes a pass in which no feed poll
failed.

`heartbeat` separates four things the old single timestamp conflated:
`last_tick_completed_at` (the scheduler loop finished a pass, any outcome),
`last_successful_tick_at` (a pass with zero failed polls),
`last_successful_poll_at` (one feed poll returned ok) and
`last_ingest_completed_at` (one episode was published into the corpus by the
watch pipeline). A failed poll stamps `last_failed_poll_at` and
`last_poll_error` and never advances a success stamp. `freshness.state` is
`never` before the first completed pass, `fresh` while the last pass completed
within `stale_after_sec`, and `stale` otherwise; `stale` means the scheduler
thread is dead or hung even though the HTTP process still answers.
`uoink doctor` reports the same block under `heartbeat` and fails on `stale`.

### `POST /extract`

Body:

```json
{"url": "https://www.youtube.com/watch?v=...", "interval": 30}
```

Response on success:

```json
{
  "ok": true,
  "folder": "C:\\Users\\you\\Desktop\\Uoink\\<slug>",
  "combined_md": "# Title\n\n...",
  "screenshot_count": 12,
  "title": "Original video title"
}
```

The result folder remains available from the dashboard and tray menu; a
background capture does not pop File Explorer open.

Response on failure:

```json
{"ok": false, "error": "ffmpeg failed: ..."}
```

## CORS

Allowed origins: `https://www.youtube.com`, `https://youtube.com`.
Methods: `GET, POST, OPTIONS`. Headers: `Content-Type`. Preflight handled.

If you hit a CORS error from somewhere else, edit `ALLOWED_ORIGINS` in
`server.py`.
