# Local Server (`server.py`)

The browser extension talks to this server at `http://127.0.0.1:5179`.
It runs the same yt-dlp + ffmpeg pipeline as the dashboard and extension,
exposed through a loopback JSON API. User-data and mutating routes are
authenticated; bounded liveness and product-metadata routes are public.

## Dependencies

The HTTP server uses the Python standard library, so it does not need
FastAPI, Flask, or Uvicorn. The Uoink application still needs its pinned
Python packages, yt-dlp, and ffmpeg.

Follow [REQUIREMENTS.md](REQUIREMENTS.md) for the complete source setup.
Do not install an unpinned subset from this page. Startup notifications use
the platform integration in `_platform.py`; `win11toast` is not used.

## Running

After completing [REQUIREMENTS.md](REQUIREMENTS.md), run:

```
python server.py
```

Keep that terminal open while developing. For a background launch,
double-click **`start_server.bat`** or run:

```powershell
.\start_server.ps1
```

Both launchers prefer the installed bundled interpreter, then the source
checkout's `.venv`, then `pythonw` on `PATH`.

Verify it's alive at `http://127.0.0.1:5179/ping`. A live helper returns HTTP
200 with `"ok": true`; the full response shape is documented below.

Logs are written to `server.log` next to `server.py`.

## Auto-start at login

The Windows installer creates and removes Uoink's login autostart entry. A
source checkout does not change login state. If you deliberately add a
shortcut to `start_server.bat` under `shell:startup`, remove that shortcut
yourself when you no longer want the development helper at login. Do not kill
every `pythonw.exe` process; other Python applications may use it.

## Endpoints

### `GET /ping`

Values vary with the installed version, selected Whisper model, downloaded
models, output-root recovery, and corpus state. The response shape is:

```json
{
  "ok": true,
  "version": "<current version>",
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

### `POST /extract`

Every POST route is token-gated. Read the source-checkout token from
`token.txt` beside `server.py` and send it in the `X-Uoink-Token` header.
Installed copies use `%LOCALAPPDATA%\Uoink\token.txt`.

PowerShell request:

```powershell
$headers = @{
  "X-Uoink-Token" = (Get-Content .\token.txt -Raw).Trim()
}
$body = @{
  url = "https://www.youtube.com/watch?v=..."
  interval = 30
} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:5179/extract `
  -Method Post -Headers $headers -ContentType "application/json" -Body $body
```

Response on success:

```json
{
  "ok": true,
  "folder": "C:\\Users\\you\\Desktop\\Uoink\\<slug>",
  "yoink_md": "# Title\n\n...",
  "corpus_md_paste": "# Title\n\n...",
  "screenshot_count": 12,
  "title": "Original video title",
  "video_slug": "original-video-title"
}
```

The response also carries caption/transcript provenance and long-video mode
fields. On success the helper asks the OS to reveal the result folder.

Response on failure:

```json
{
  "ok": false,
  "error": "<plain-language failure>",
  "error_detail": "<sanitized diagnostic detail>",
  "failure_phase": "screenshots"
}
```

## CORS

Page origins are limited to `https://www.youtube.com`,
`https://m.youtube.com`, and `https://youtube.com`; Chromium extension origins
are accepted separately. Preflight allows `GET`, `POST`, `DELETE`, and
`OPTIONS`, plus `Content-Type`, `X-Uoink-Token`, `X-Uoink-Client`,
`X-Yoink-Token`, and `X-Yoink-Client`. The helper also emits the Private
Network Access response header required for browser-to-loopback requests.

Do not broaden CORS to work around a failed request. Check the request origin,
Host, token header, and `/token` client header against
[docs/security.md](docs/security.md).
