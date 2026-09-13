"""Observe one public metadata redirect without following it."""
import sys
if tuple(sys.version_info[:3]) != (3, 14, 6) or not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode) or "site" in sys.modules:
    raise RuntimeError("Isolated stdlib interpreter required")
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request

out = Path(__file__).absolute().parent / "redirect01"
out.mkdir(exist_ok=False)
url = "https://huggingface.co/api/models/mobiuslabsgmbh/faster-whisper-large-v3-turbo?blobs=true"
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
receipt = {"url": url, "started_utc": datetime.now(timezone.utc).isoformat(), "redirect_followed": False, "asset_downloads": 0, "plan_accepted": False}
code = 1
try:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "uoink-public-metadata-review/1"})
    try:
        response = opener.open(request, timeout=12)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        body = response.read(4097)
        receipt.update(status=response.code, location=response.headers.get("Location"), content_type=response.headers.get("Content-Type"), final_url=response.geturl(), body_truncated=len(body) > 4096)
        (out / "body.txt").write_bytes(body[:4096])
        receipt.update(body_bytes_retained=min(len(body), 4096), body_sha256=hashlib.sha256(body[:4096]).hexdigest())
    code = 0
except Exception as exc:
    receipt["failure"] = {"type": type(exc).__name__, "message": str(exc)}
receipt.update(diagnostic_exit=code, finished_utc=datetime.now(timezone.utc).isoformat())
(out / "result.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print(json.dumps(receipt))
raise SystemExit(code)
