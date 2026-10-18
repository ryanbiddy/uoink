# Surface map: DNS-rebinding defense (C-04)

CRIT-4. "Private, on your disk" was defeated by visiting a web page: with
no Host-header validation, a malicious site could rebind its own domain to
127.0.0.1 and then have the victim's browser drive the entire local API,
steal the token, and read the whole corpus. This surface is the wall.

## The attack

1. Victim visits `evil.attacker.com`. Its DNS answers with the real server
   IP first, then re-answers with `127.0.0.1` (rebinding).
2. The victim's browser now sends `fetch("http://evil.attacker.com/...")`
   to the local Uoink helper, carrying `Host: evil.attacker.com`.
3. Same-origin from the browser's view (it's still `evil.attacker.com`),
   so the page reads every response.

The one thing every rebind request shares: the Host header is the
attacker's domain, never loopback.

## The defense: Host allowlist

`Handler._host_allowed()` -> `_reject_bad_host()` runs as the FIRST line of
`do_GET`, `do_POST`, `do_DELETE`, and `do_OPTIONS`, before the public
probes, before the token check, before the body is read. A failing Host
gets `403 {"ok": false, "error": "forbidden host"}` and a logged warning.

Rules:
- Hostname must be in `ALLOWED_HOST_NAMES` (`127.0.0.1`, `localhost`,
  `::1`/`[::1]`). A real domain is never in this set.
- If the Host carries a port, it must equal the port the server is
  actually bound to (`self.server.server_address[1]`), so the check holds
  whatever port an install lands on, not a hardcoded 5179.
- A missing Host (HTTP/1.0, hand-rolled clients) passes: it can't carry a
  rebind target.

Local processes (curl, scripts on the same machine) can still set
`Host: localhost` and reach the API. That's unchanged and intentional:
they already run as the user and could read `token.txt` directly. This
defense is against the BROWSER-driven rebind, which is the CRIT-4 vector.

## /token hardening

- **Extension-id pin** (`_allowed_extension_ids()`): on by default. The
  public manifest key fixes Uoink's Chromium ID at
  `bkcapfidedhfcjpmjabeopfbcjcbmdmi`. The helper always includes that ID and
  unions IDs from `UOINK_EXTENSION_IDS=<id>[,<id>]` and `settings.extension_ids`.
  Previously, a nonempty environment variable replaced the settings list.
  Extension origins must match an allowed ID exactly, for both `/token` and CORS.
- **Origin-carrying extension POST**: the extension uses a bodyless
  `POST /token` so Chromium sends `Origin: chrome-extension://<id>`.
  Worker GETs can omit Origin and send `Sec-Fetch-Site: none`; the Host wall
  alone cannot distinguish those workers, so that token path is now refused.
- **Same-origin page GET**: missing Origin is accepted only with
  `Sec-Fetch-Site: same-origin` and a present, allowed loopback Host. This
  preserves the helper-served dashboard in browsers, tray WebView2 and the
  Tauri dashboard window. Requests with `none` or missing fetch metadata
  receive HTTP 403. See [local-client compatibility](../security.md) for the
  existing splash-header mismatch and older WKWebView limitation.

## Layered posture (after C-04)

1. **Host allowlist** (new) -- blocks the rebind for every verb, first.
2. Token (`X-Uoink-Token`) on all private routes.
3. `/token` CSRF gate: `X-Uoink-Client` header + pinned/configured extension
   Origin (or the same-origin page proof above) + per-install rate limit.
4. CORS ACAO allowlist (pinned/configured extension origins + YouTube).

## Tests / proof

`tests/test_c04_dns_rebinding.py` drives raw HTTP by hand (urllib would set
Host from the connection target, hiding the bug):
- red on unpatched main: `Host: evil.attacker.com` on `/health` answers
  200; green: 403.
- spoofed Host rejected on the public probe, on a token-gated GET even
  with a valid token, and on a POST -- the rebind's real goal.
- loopback hosts (`127.0.0.1:<port>`, `localhost`, bare, absent) still
  pass.
- the extension-id pin: the default pinned ID passes, unlisted IDs receive
  403, and an explicitly allowed ID passes.
- `/token` rebind blocked at the Host wall.

`tests/test_sec_token_pin.py` exercises the real handler over in-memory HTTP,
including pinned-origin POST, foreign-origin rejection and refusal of an
originless `Sec-Fetch-Site: none` GET. Its Node harness executes the shipped
extension's bootstrap and refresh code with fake fetch and storage.
