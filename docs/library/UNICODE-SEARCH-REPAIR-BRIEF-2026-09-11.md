# Unicode search repair

Ryan requested the remaining fixes after the September 11 status report. SEC-06
is a product defect: index._fts_query accepts only ASCII terms, so Japanese
queries disappear and accented words split. Repair query tokenization without
changing schema, opening ordinary data, or relaxing the quoted FTS grammar.

Use a separate worktree and fresh disposable indexes. Add independent regression
coverage for Japanese, accented Latin, another non-Latin script, mixed text,
combining marks, prefix matching, and FTS operators supplied as user text. Check
actual retrieval as well as the query string. Preserve existing ASCII behavior
and all original tests. Run the new tests, index/search companions and the
security findings suite in worker and checkout with the guarded native runner.

The original SEC-06 test has strict xfail. Leave that marker and its assertions
unchanged. First retain the ordinary post-repair result, which should report
XPASS(strict) if the assertion succeeds. Then use pytest --runxfail to execute
the same assertions normally; record that option and the new outcome explicitly.
The final complete tree may use --runxfail for this repaired expectation, with
case membership and unchanged original test bytes verified. The historical
xfail and unavailable AT6 exit remain separate evidence; neither is rewritten.

No ordinary index, port 5179, model invocation, external source fetch, paid API,
speaker run, automatic filing or existing acceptance-test edit is authorized.
Integrate through raw diff and three-way apply after independent verification.
This changes packaged source and joins the browser fix before final validation,
replacement packaging and fresh installed observations.
