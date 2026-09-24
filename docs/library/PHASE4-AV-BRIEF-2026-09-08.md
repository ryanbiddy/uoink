# Phase 4 implementation brief, run AV (2026-09-08)

Fable's dispatch under `ORCHESTRATION-V1-2026-09-04.md`. Contract `phase4-v1-2026-09-08`
([PHASE4-CONTRACT-2026-09-08.md](PHASE4-CONTRACT-2026-09-08.md), Astra) is frozen and governs;
this brief adds the reconciliation the contract asked Fable for, the file ownership, and a
frozen module interface so the implementer and the test author code against the same names.
Base: the commit this brief lands in. No worker runs a model, the resident helper, or touches
port 5179 or the live index. Never import or start the real backend against default settings
in a test. Do not commit; Fable integrates and runs every test.

## Reconciliation of the two AU companion documents against the contract

Read before acting. None of these amends a frozen gate.

1. **Claude Code CLI 2.1.261 has no native resource reader** (protocol-limits note, section
   3.5). `read_library_resource(uri)` is therefore the retrieval path P4-14 will actually
   exercise; the resource methods are still implemented and tested over stdio, and AW records
   native support as absent, not failed. Nothing in the contract changes.
2. **Prompt arguments split on whitespace** in the CLI (note, section 7.2). The prompt set is
   unchanged; `docs/claude-code-mcp.md` (AV-2) documents single-token or hyphenated topics.
   `prompts/get` still receives arbitrary strings from other clients and validates them.
3. **No SDK migration for stdio.** The client negotiates `2025-11-25` over stdio; the pinned
   FastMCP serves it. Do not bump `mcp` or add a protocol date. Fable records the SDK drift
   (requirements pin `mcp==1.27.1`; the note observed 1.26.0 in the worktree environment; the
   orchestration environment has 1.28.1) and the installed build's bundled version decides.
4. **Test file names** follow the contract's reservations, finalized here:
   `tests/test_library_resources.py` (P4-01, P4-02, P4-03, P4-05),
   `tests/test_library_resource_trust.py` (P4-04), `tests/test_library_prompts.py` (P4-07),
   `tests/test_phase4_stdio.py` (P4-06, P4-13 stdio part), and in AV-2
   `tests/test_library_briefs.py` (P4-08) and `tests/test_library_mirror.py` (P4-09 to
   P4-12). Gemini's plan sections 2, 3 and 6 fold into the first four files; sections 4 and
   5 into the AV-2 files. Gemini's proposed file names are not used.
5. **Duplicate JSON keys.** FastMCP hands stdio handlers parsed objects, so duplicate keys are
   detectable only where raw bytes are available: the HTTP `/tools/*` route and any raw
   frame test. Reject them there; document the stdio limit in the module docstring.
6. **Error transport.** Over stdio, raise `mcp.shared.exceptions.McpError(ErrorData(code, message, data))`
   with `-32602` (invalid parameters), `-32002` (missing or deleted resource), `-32603`
   (other resource failure) and the domain envelope in `data`. Tools return the domain
   envelope as text with `isError` set by the SDK from the exception path or explicitly.

## Two increments

**AV-1 (this run):** identity and URI grammar, the five readers, curated list and templates,
the three read tools, the four prompts, refusal shapes, trust fence, deadline and rate guard,
stdio registrations. **AV-2 (next run):** brief input and publication with persistence under
`DATA_ROOT/reach/briefs/`, the opt-in mirror with its ledger under `DATA_ROOT/reach/mirror/`,
settings and consent, client artifacts and inventories. AV-1 must leave clean seams for AV-2:
`briefs/{date}/{brief_hash}` parses and reads refuse `feature_unavailable` until AV-2 lands.

## Ownership (AV-1)

| Owner | Files |
|---|---|
| claude (Fable 5.1 worker) | New `library_resources.py` (URI grammar, readers, renderer, guard) and `library_prompts.py` (four prompts, report-only readers). Additive `TOOL_REGISTRY` entries in `uoink_mcp_tools.py` for `search_library`, `get_library_item`, `read_library_resource` only (Fable releases that reservation for these additions; touch nothing else in the file). Stdio registrations in `uoink_mcp.py` for the resource and prompt methods and the three tools. |
| gemini | The four AV-1 test files above, written against the interface below and the contract's gates; fixtures per your plan section 7.2 (temporary index built with `index.Index` on a temp path, synthetic corpus files, hostile source text). Run them; they fail on import until integration and that is the acceptance target. Do not edit implementation files. |
| Fable | `server.py` (HTTP advertisement stays tools-only; `/tools/*` duplicate-key rejection), `tests/test_c01_mcp_stdio.py` inventory (25 to 28), docs and inventories in AV-2, integration. |

Astra is not in AV-1 so that AW stays independent. Grok is not dispatched.

## Frozen module interface

`library_resources.py`:

```python
CONTRACT_VERSION = "phase4-v1-2026-09-08"
RENDER_VERSION = "reach-markdown-v1"
SCHEMA_VERSION = 1
URI_PREFIX = "uoink://library/v1/"
TEMPLATES: tuple[dict, ...]   # five: {"uriTemplate", "name", "description", "mimeType": "text/markdown"}
LIMITS: dict[str, int]        # every frozen number from the contract, by a stable name

class ResourceError(Exception):
    code: str; message: str; retryable: bool; details: dict
    def envelope(self) -> dict            # {"ok": False, "schema_version", "contract_version", "error": {...}}

def refusal(code: str, message: str, *, retryable: bool = False, details: dict | None = None) -> dict
def encode_key(identity: str) -> str      # unpadded base64url of exact UTF-8; raises ResourceError on bad identity
def decode_key(key: str) -> str           # round-trip checked; raises ResourceError("invalid_request")

@dataclass(frozen=True)
class ParsedUri:
    kind: str                             # "card" | "excerpt" | "corpus" | "shelf" | "brief"
    fields: dict[str, str]                # decoded identity under "item_id"/"shelf_id"; hashes, selection, offset, length as strings

def parse_uri(uri: str) -> ParsedUri      # every rejection in the contract's grammar section is ResourceError("invalid_request")

class LibraryReader:
    def __init__(self, index, *, data_root, clock=None, deadline_s=2.0,
                 max_active=2, admissions_per_minute=60): ...
    def list_templates(self) -> list[dict]
    def list_resources(self) -> list[dict]           # curated, at most 41; raises ResourceError("library_unavailable") on storage failure
    def read(self, uri: str) -> dict                 # {"contents": [{"uri", "mimeType", "text"}]}; raises ResourceError
    def search(self, query: str, limit: int = 5) -> dict        # success envelope; raises ResourceError
    def get_item(self, *, video_id: str | None = None, slug: str | None = None) -> dict
```

`index` is an `index.Index` instance (the Phase 2 service takes the same object); tests build
one on a temporary path. `data_root` is the directory `DATA_ROOT/reach/` will live under;
AV-1 reads nothing from it. `clock` returns seconds as a float (monotonic for deadlines,
wall for `as_of`); the constructor takes both when needed as `clock` and `wall_clock`.

`library_prompts.py`:

```python
PROMPTS: tuple[dict, ...]     # four: {"name", "description", "arguments": [{"name", "description", "required"}]}

def get_prompt(reader: LibraryReader, work_service, name: str, arguments: dict[str, str]) -> dict
    # {"description": str, "messages": [instruction_message, fenced_data_message]}
    # raises ResourceError("invalid_request") for unknown name/argument, missing required, bad date/number
```

`work_service` is a `library_work.LibraryWorkService` or `None`; with `None`, `whats-new`
reports an explicit coverage gap and `reshelve-review` refuses `feature_unavailable`. Read
previews and queue state with report-only queries; never call `list_work` (it reaps leases).

Success envelopes: `{"ok": True, "schema_version": 1, "contract_version": CONTRACT_VERSION, ...}`.
Domain codes exactly as frozen. `read_library_resource(uri)` returns
`{"ok": True, ..., "contents": reader.read(uri)["contents"]}`; identical text, one renderer.

## Implementation rules that the contract leaves to the implementer

- Card resource text is exactly `library_cards.card_text(build_card(item, clips, corpus_text=read_corpus_head(path)))`
  with the default librarian profile; `card_hash` and `source_revision` come from that card,
  and `selection` must equal `library_cards.SELECTION_VERSION`. Any mismatch is
  `revision_unavailable`, not a recomputation under the old address.
- Excerpt identity is the card builder's existing excerpt id (pre-truncation); resolve it by
  rebuilding the card and matching ids, then return the untruncated source text of that
  excerpt bounded to 2,000 code points with `truncated` and original length.
- Corpus chunks: stream-hash the whole file (`hashlib.sha256`, 1 MiB blocks), refuse above
  16,777,216 bytes, verify size and mtime before and after the read, UTF-8 boundary rules
  as frozen, local paths redacted with explicit spans.
- Shelf pages: `shelf_revision` is SHA-256 over `library_cards.serialize_card` of the
  canonical structure the contract names; recheck member deletion on every read.
- Deadline: measure from admission; on overrun refuse `deadline_exceeded` and do not retry.
  Concurrency and rate: a module-level guard shared by tools, resources and prompts in one
  process; `rate_limited` carries integer `retry_after_ms` at most 60,000.
- Trust fence: reuse `library_cards` canonical JSON escaping inside a fixed preface and
  fence; render link destinations separately from labels; `invalid_source_data` on an
  unsafe URL, terminal control or leaked path in a hashed card.
- Stdio: register the low-level handlers (`list_resources`, `list_resource_templates`,
  `read_resource`, `list_prompts`, `get_prompt`) on `mcp._mcp_server` so the curated list
  and error codes are ours, and advertise resources `{"subscribe": false, "listChanged": false}`
  and prompts `{"listChanged": false}` only when those handlers exist. Keep stdout
  protocol-clean; diagnostics to stderr.
- No new schema, no migration, no edits to `library_work.py`, `library_cards.py`,
  `source_subscriptions.py`, prompts, or Phase 2/3 tests.

## What each worker returns

- claude: the files above plus a short note at the top of `library_resources.py` naming every
  contract rule you could not implement exactly and why; list the pytest commands Fable must
  run. You cannot run a shell.
- gemini: the four test files, a fixture module if shared, and the command that runs them.
