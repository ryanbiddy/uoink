# Isolated credential-store repair, 2026-09-09

Gemini Role B found, and Astra confirmed at c3da3f6, that server.py uses the
ordinary Uoink keyring service for isolated helpers and falls back to Yoink.
GET settings therefore reads an ordinary saved key; a key update or 401 can
change/delete the ordinary entry. File/profile isolation does not cover this
service. No real credentials have been queried for this diagnosis.

Repair only server.py and add tests/test_isolated_credential_store.py. Update
docs/security.md for the exact new behavior. Do not edit existing tests, Inno,
receipt fixtures or other production code. Do not run any actual OS keyring
operation, installation, model/client, source fetch, or paid API. Never touch
the live index or port 5179. No commits; write source and regression file early.

In isolated mode use a deterministic service name derived from the validated
canonical profile path, distinct from ordinary Uoink and legacy Yoink. Use a
bounded collision-resistant hash, not just port: two profiles sharing a port
must not share credentials, and a profile changing port retains its identity.
Read, set and delete must select that same namespace. Isolated reads must never
fall back to ordinary/legacy services. Normal mode retains existing Uoink/Yoink
behavior. Plaintext migration may only write the isolated namespace. Inspect all
server key access callers; do not print or persist key material in tests/logs.

Use a recording fake keyring exclusively. Add regressions for isolated read,
set, delete, absent-key no fallback, profile separation/same-port, stable profile
identity and ordinary legacy compatibility. Test a 401/reset path if practical
without HTTP/network, and public-settings behavior with the fake backend. Every
test must assert no calls to ordinary services in isolated mode. Use no paid key
environment variable, even a fake ANTHROPIC_API_KEY.

First observe the new regression failures against unchanged production source,
retain the result, then repair and run the corrected file plus existing settings,
credential, isolation and security companions resolved by git ls-files. Use the
guarded integrator runner supplied from the checkout: set IG_FORBIDDEN_LIVE to
the forbidden path string before invoking its native Python; --root is your own
worktree and each --label is fresh. Do not reference another checkout in product
code. Astra independently runs the same named suites in your worktree and after
raw diff / three-way integration. Preserve every failed attempt and reason.

Deliver docs/library/RYAN-ISOLATED-CREDENTIAL-WORKER-2026-09-09.md with exact
commands/results and residual limits. This changes packaged server.py: rebuild
and reseal before installed or new bundled verification. No existing artifact
is replaced in place and no old measurement gains credit for this repair.
