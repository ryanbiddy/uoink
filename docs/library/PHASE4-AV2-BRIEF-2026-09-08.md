# Phase 4 implementation brief, second increment (run AV-2, 2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Contract `phase4-v1-2026-09-08`
([PHASE4-CONTRACT-2026-09-08.md](PHASE4-CONTRACT-2026-09-08.md)) governs; the sections "Brief
generation belongs to the client" and "Opt-in corpus mirror" are the specification for this
increment and are not restated here. AV-1 is integrated at `82e973a` (readers, tools,
prompts, stdio). Base: the commit this brief lands in. No worker runs a model, the resident
helper, or touches port 5179 or the live index. Do not commit; Fable integrates and runs
every test.

## Ownership (AV-2)

| Owner | Files |
|---|---|
| claude (Fable 5.1 worker) | New `library_briefs.py` and `library_mirror.py` to the interface below; the two brief tools `get_library_brief_input` and `publish_library_brief` added to `TOOL_REGISTRY` (additive; `publish_library_brief` labelled as a local write) and to stdio in `uoink_mcp.py`; `briefs/{date}/{brief_hash}` reads and the curated list's "latest valid brief" entry wired into `library_resources.py` through the store (replace the `feature_unavailable` placeholders only). Event hooks: expose `library_mirror.on_committed_event(...)` and call it from the smallest possible seams in `library_work.py` (apply, undo, pin) and `server.py` (capture commit, source refresh, restore, deletion), each a one-line call guarded so a missing or disabled mirror is a no-op; name every seam in your report. |
| gemini | `tests/test_library_briefs.py` (P4-08) and `tests/test_library_mirror.py` (P4-09 to P4-12) against the interface below and the contract's gate table, folding your plan's sections 4 and 5 (deletion, tombstones, mirror edge cases); fixtures per `tests/phase4_fixtures.py` plus a temporary vault directory and a fake volume marker. Run them; they fail on import until integration. |
| Fable | Settings plumbing in `server.py` (`library_mirror_enabled`, consent record, the dashboard intent route for enabling the mirror), the dashboard panel, integration, and the AW candidate. |

Astra rules later (run AW) and is not in AV-2. Grok has delivered the client docs, skill and
bundle docs (AV-2a to AV-2c).

## Frozen interface

`library_briefs.py`:

```python
CONTRACT_VERSION = "phase4-v1-2026-09-08"
BRIEF_DIR = "reach/briefs"                      # under data_root

class BriefStore:
    def __init__(self, index, work_service, *, data_root, clock=None, wall_clock=None): ...
    def prepare_input(self, date: str, run_id: str) -> dict
        # success envelope: job_key, input_hash, as_of, bindings (queue digest, run revision,
        # taxonomy/projection revisions, latest covered operation sequence, interval),
        # counts, coverage, work rows (<= 20), cards (<= 5 default Librarian), sampling note.
        # Packet <= 24,576 UTF-8 bytes; no lease, no mutation. Raises ResourceError.
    def publish(self, *, job_key: str, input_hash: str, input_packet: dict, submission_key: str,
                document: str, citations: list[dict], usage: dict | None,
                client_identity: str) -> dict
        # rebuilds and checks the packet against current data; serializes writers across
        # processes; idempotent on (submission_key, request hash); returns the receipt.
        # Refusals: stale_brief, brief_conflict, idempotency_conflict, invalid_request,
        # resource_too_large, library_unavailable, deadline_exceeded, rate_limited.
    def latest_valid(self, utc_date: str) -> dict | None      # {"date", "brief_hash", "uri", "accepted_at"}
    def read(self, date: str, brief_hash: str) -> dict         # rendered document for briefs/{date}/{brief_hash}; refuses when a dependency changed or was deleted
    def purge_dependents(self, video_id: str) -> dict          # hard-purge hook: removes owned artifacts and stored packets; keeps content-free receipt hashes
```

`library_mirror.py`:

```python
CONTRACT_VERSION = "phase4-v1-2026-09-08"
MIRROR_LEDGER_DIR = "reach/mirror"              # under data_root
MIRROR_ROOT = "Uoink"                           # under the resolved vault
SCOPE_ALL = "all_current_and_future_items"

@dataclass(frozen=True)
class MirrorConsent:
    destination: str; scope: str; allowlist: tuple[str, ...]; consented_at_ms: int; marker: str

class Mirror:
    def __init__(self, index, reader, brief_store, *, data_root, consent: MirrorConsent | None,
                 enabled: bool, clock=None, wall_clock=None): ...
    def preview(self, destination: str, scope: str, allowlist: list[str] | None = None) -> dict
        # planned paths, counts, the third-party indexing notice, existing-file conflicts; no writes
    def status(self) -> dict     # pending, synced, stale, conflicts, deletion_pending, destination state
    def resync(self, *, max_files: int = 20, budget_s: float = 2.0) -> dict
        # validates the volume marker, drains pending deletions first, then content writes
    def on_committed_event(self, kind: str, *, video_id: str | None = None,
                           shelf_id: str | None = None, brief_hash: str | None = None) -> None
        # kinds: capture, source_refresh, apply, undo, pin, brief_published, restore, soft_delete, hard_purge
        # records desired generation; performs no I/O beyond the ledger
    def tombstone(self, video_id: str) -> dict
    def purge(self, video_id: str) -> dict         # idempotent; reports purge_blocked_user_edit
    def restore(self, video_id: str) -> dict
```

Both modules reuse `library_resources` for the refusal envelope, budgets, guard, safe rendering
and link validation; no second renderer. Paths, hashes, atomic-write, ownership-manifest,
volume-marker, tombstone and deletion rules are the contract's, verbatim. All vault I/O
runs in a cancellable worker with the 2 s and 20-file bounds; a disconnected destination is
`destination_unavailable` and the primary operation still succeeds.

## What each worker returns

- claude: the files above, the list of event seams, any contract rule you could not
  implement exactly (at the top of each module), and the pytest commands. You cannot run a
  shell.
- gemini: the two test files and their fixtures, and the command that runs them.
