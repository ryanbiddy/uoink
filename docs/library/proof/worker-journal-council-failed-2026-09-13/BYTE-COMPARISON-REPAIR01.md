# Council text comparison repair

The first data-only comparison559926 returned exit1 at ASTRA-WORKER-BOOTSTRAP-VERDICT-2026-09-13.md before writing its comparison JSON or applying a worker patch. Its tool result was reported in the conversation but was not retained as a raw object; this note does not reconstruct one.

The correction will distinguish canonical Git bytes from checkout line endings for only the two selected top-level Astra verdict documents. All selected proof sources, tests and receipts still require raw equality. A verdict difference is accepted only if replacing CRLF with LF yields the exact pinned canonical Git bytes; preserve both raw variants and report their hashes. Any other difference remains a failure. This changes the documentary comparator, not source, cases, worker output or execution evidence. No test or worker rerun follows this preparation failure.
