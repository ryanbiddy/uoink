# Collector console-display correction

Before the third request, 2026-09-13: both first requests completed with HTTP 200 and actual process exit 0. Their complete request/result JSON and exact response bytes are retained. The console-only summary incorrectly piped an OrderedDictionary into Select-Object, producing null display fields. Cast that dictionary to PSCustomObject before selecting display fields. This changes no request, bound, retained response, result JSON or exit outcome. Preserve the first collector under collector-draft01; do not repeat the two successful requests.

The same pre-request review found that the initial source-path regex required a directory before LICENSE, unintentionally refusing a repository-root LICENSE. Use an explicit alternative for that exact root filename and .gitattributes, retaining the same immutable-commit and public-repository restrictions. No source request or refusal had yet occurred.
