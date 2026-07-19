# Corpus read contract v1

Uoink exposes a token-gated, read-only contract for the writing product and
other local corpus consumers. The version is present in both the URL and every
JSON envelope:

```json
{
  "ok": true,
  "contract": "uoink.corpus.read",
  "version": 1,
  "operation": "search",
  "data": {}
}
```

## Endpoints

| Method | Path | Result |
|---|---|---|
| GET | `/api/corpus/v1/search` | path-free item references plus paging state |
| GET | `/api/corpus/v1/items/<id>` | one item, Markdown content, attachment descriptors |
| GET | `/api/corpus/v1/facets` | corpus-wide counted facets and capture-date bounds |
| GET | `/api/corpus/v1/taste` | consolidated taste Markdown and explicit anchors |
| GET | `/api/corpus/v1/items/<id>/attachments/<attachment-id>` | one contract-listed image |

All routes require `X-Uoink-Token`. Search accepts `q`, `channel`, `topic`,
`hook_type`, `platform`, `source_type`, `author`, `date_from`, `date_to`,
`limit`, and `offset`. `limit` is 1 through 200; dates are `YYYY-MM-DD`.
Unknown parameters return `invalid_request`.

## Boundary rules

- Responses never expose `corpus_path`, `sidecar_path`, the data root, or a
  token path.
- An item reference carries generic creator credit, source taxonomy, capture
  time, facets, and an optional preview descriptor.
- `get` returns Markdown as data. Missing corpus files produce
  `content.available: false`, so one stale path does not hide the item.
- Content reads are capped at 2 MiB and report the original byte count plus a
  `truncated` flag.
- Attachments are generic image descriptors (`kind`, `role`, media type,
  label, size, contract URL). A resolved file must remain inside that item's
  corpus folder.
- Provider output is exact-key validated. Unknown fields fail conformance
  instead of silently becoming public API.

## Errors

Contract handlers return the same envelope metadata with `ok: false`:

```json
{
  "ok": false,
  "contract": "uoink.corpus.read",
  "version": 1,
  "operation": "get",
  "error": {
    "code": "not_found",
    "message": "corpus item not found",
    "retryable": false
  }
}
```

Stable v1 codes are `invalid_request`, `not_found`, `unavailable`, and
`provider_nonconformant`. Authentication fails before contract dispatch and
keeps the helper's existing 403 response.

## Provider conformance

`corpus_contract.py` owns request validation, the provider protocol, envelopes,
and exact response validation. `corpus_provider.py` implements those reads over
Uoink's current SQLite index and corpus files.

The checked-in provider fixture is
`tests/fixtures/corpus_contract_v1/provider.json`. It carries its rewrite and
no-write check commands. Regenerate only after reviewing the contract change:

```powershell
python tests/regenerate_corpus_contract_v1_fixture.py
python tests/regenerate_corpus_contract_v1_fixture.py --check
```

The Generate tab is the first consumer. Its source list, counted topic, hook,
and channel facets, and selected-source detail now come through v1. Writing
grounding also adds the v1 item and path-free taste subset while retaining the
old grounding fields for the extraction compatibility window.
