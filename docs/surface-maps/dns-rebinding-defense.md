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

- **Extension-id pin** (`_allowed_extension_ids()`): off by default
  (load-unpacked gives every dev a different id, and no Chrome Web Store id
  is published yet). Set `UOINK_EXTENSION_IDS=<id>[,<id>]` (or the
  `extension_ids` settings key) and `/token` mints the token only for those
  extension origins. Until then any `chrome-`/`moz-extension` origin is
  accepted, exactly as before. When Ryan has the CWS id, one env var locks
  it.
- **Absent-Origin trust, revisited**: `/token` still trusts a missing
  Origin (genuine same-process service-worker fetches from Chromium forks
  like Comet send none). C-04's judgment: this is now safe because the Host
  allowlist runs first and a rebind always carries the attacker's Host, so
  trusting a missing Origin no longer widens the rebind surface. The
  narrower alternative (rejecting absent Origin) would relock the forks
  this rule was added for, with no security gain once Host is validated.

## Layered posture (after C-04)

1. **Host allowlist** (new) -- blocks the rebind for every verb, first.
2. Token (`X-Uoink-Token`) on all private routes.
3. `/token` CSRF gate: `X-Uoink-Client` header + extension Origin
   (+ optional id pin) + per-install rate limit.
4. CORS ACAO allowlist (extension origins + youtube).

## Tests / proof

`tests/test_c04_dns_rebinding.py` drives raw HTTP by hand (urllib would set
Host from the connection target, hiding the bug):
- red on unpatched main: `Host: evil.attacker.com` on `/health` answers
  200; green: 403.
- spoofed Host rejected on the public probe, on a token-gated GET even
  with a valid token, and on a POST -- the rebind's real goal.
- loopback hosts (`127.0.0.1:<port>`, `localhost`, bare, absent) still
  pass.
- the extension-id pin: unpinned accepts any extension, pinned-out 403s,
  pinned-in passes.
- `/token` rebind blocked at the Host wall.

Full suite 177 passed.
