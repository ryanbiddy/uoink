2026-09-13: vpr02 ran all 76 frozen cases with a valid guard. It recorded 75
passed, 1 failed, 0 skipped in 0.728283 seconds. Actual child, launcher/outer
and invoking tool exits were all 1. Inputs and lexical wrappers remained
unchanged; no heavy imports or unexpected audit events were recorded.

The failed json_deep-nesting case constructs 2,000 nested JSON arrays within
the bounded header. This interpreter parsed that document; the reader then
rejected it at the fixed 54-key schema gate. The frozen assertion expected a
malformed JSON refusal. The observed error was an AssertionError comparing
'Malformed UTF-8 JSON' with 'Fixed 54-key tensor schema mismatch'. The payload
was refused, but this does not pass the asserted early structural bound.

Root classified this as a reader robustness contract defect, not a fixture
issue. Prepare a separate source repair with a fixed structural-depth limit
before json.loads, counting only unquoted braces/brackets and respecting
string escapes. Do not rely on interpreter recursion behavior or change its
recursion limit. Preserve all 76 assertions. No source repair or rerun occurred
as part of this execution archive.

The earlier vpr01 setup failure and the 26- and 25-payload preparations remain
sealed unchanged. This archive retains exact vpr02 inputs, raw membership and
guard report, child result, launch plan, admission and actual outer/tool exits.
No real artifact, package, model, network or installer operation occurred.
