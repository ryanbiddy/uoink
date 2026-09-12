# Client evidence export review

Export only explicitly selected client streams, original MCP frames, action
hooks, prepared noncredential configuration, operator receipts and diagnostic
instruments. Exclude credential directories, raw authentication/debug logs,
one-use sign-in material, bearer-token files and databases. Preserve original
payload bytes with a per-directory Git attributes rule and verify committed
blob hashes afterward. This is a proof addendum, not a passing release verdict.

The first exporter preflight stopped before creating its output directory.
It incorrectly required every PreToolUse to have a PostToolUse success event.
Actual hooks include one PostToolUseFailure for the original ordinary session's
invalid guessed URI and two for the media session's storage refusals.

Repair the exporter to match each pre-event against exactly one terminal
PostToolUse or PostToolUseFailure event by tool-use id, and retain each count
separately. Never map failure events to successful tool outcomes. Preserve the
initial exporter and its failed preflight. This changes only the serializer's
evidence accounting; original action records and all client results stay intact.

The second preflight also stopped before output creation: its credential-prefix
screen matched the screen's own source literal. Require a credential-shaped
value instead of a bare prefix, retaining the credential-directory and filename
exclusions. Both failed exporter versions are included as instruments. Neither
attempt copied credential material or produced a client measurement.
