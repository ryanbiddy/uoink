# Writer compatibility window

CM-13 creates Writer as a separate private product while keeping the current
Uoink dashboard available during migration.

## Current ownership

- Uoink owns Capture, the corpus, facets, taste, engagement, and corpus
  assembly.
- Writer owns new drafts, prose versions, scripts, critique records, voice
  samples, Voice DNA, and shot-list files in its repository and database.
- Uoink's existing `/writing/*`, `/script/*`, `/scripts`, `/workspace/*`, and
  Generate-tab paths remain in place as the rollback surface. Their default
  behavior is unchanged in this compatibility release.

The old and new stores are separate modes. Uoink does not mirror a save into
Writer, and Writer does not open Uoink's database. This avoids silent dual
writes while existing Uoink work remains readable.

## Local peer check

Uoink exposes one authenticated, read-only check:

```text
GET /api/writer-peer/v1/status
X-Uoink-Token: <Uoink local token>
```

The response contains availability, Writer's API version, path-free counts,
and the active compatibility mode. It never returns a URL, credential,
database path, draft body, or source metadata.

Writer's public liveness probe can be detected without configuration. Private
status requires process-owned configuration:

```powershell
$env:UOINK_WRITER_URL = "http://127.0.0.1:5181"
$env:UOINK_WRITER_TOKEN = "<Writer local credential>"
python server.py
```

Uoink does not read Writer's credential file. The URL is restricted to HTTP
loopback with an explicit port.

## Failure behavior

Writer can be stopped, absent, unconfigured, or running an incompatible
contract without affecting Capture or Generate. The peer check reports the
state and performs no repair, launch, write, or fallback action.

The later cutover must choose one write owner per mode. It must not fall back
from a failed Writer save to a Uoink save, because an uncertain response could
create two divergent versions. Until that cutover is separately gated, the
existing Uoink routes remain the active compatibility owner.

## Gates

Before removing any Uoink writing route:

1. Writer's full tests, wheel check, HTTP smoke, and MCP registration pass.
2. Writer's pinned CM-7 parity fixture passes for writing, scripts, critique,
   and assembly inputs.
3. Uoink regenerates all three CM-7 fixtures with exact output.
4. Uoink's full suite and doctor pass.
5. A user-triggered data move and rollback procedure are tested separately.

Rollback for this compatibility stage is to unset the two peer environment
variables or revert the CM-13 Uoink commit. Capture and Generate remain on the
unchanged monolith paths in either case.
