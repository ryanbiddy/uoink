# Finish the local-wheel builder boundaries before acceptance

Astra independently inspected a provisional a332397f wheel: all 512 RECORD
entries verify, the six expected files differ and every remaining payload and
dependency declaration matches upstream. That artifact check passes. It does
not accept the builder's broader claims or its new tests.

The inspected builder hashes one read but then reopens the wheel for parsing;
its path helper swallows permission/other filesystem errors. Archive duplicates
are case-sensitive, RECORD duplicates silently overwrite entries, and metadata
validation can accept duplicate singleton headers. Its global sys.modules check
can reject an unrelated caller that already imported NLTK. The new test repeats
that global-state assumption. Ambient SOURCE_DATE_EPOCH changes the supposedly
fixed artifact. These are concrete source-review findings; no exploit or failed
product measurement is claimed by this brief.

Wait for the worker to finish and preserve its exact source, proposed tests,
reports, artifacts and every attempt before repair. Do not change a running
worker's files. Preserve the independently checked provisional wheel and raw
results. Add negative controls against the preserved builder and retain their
actual outcomes before accepting any replacement.

Repair only scripts/build_nltk_pathsec_wheel.py and its unaccepted new tests.
Read, hash and parse the same wheel bytes; refuse filesystem errors; validate
case-normalized archive names, RECORD uniqueness and singleton metadata.
Use the accepted source preparation without importing NLTK or depending on
whether another caller imported it. Put that import observation in a fresh
child process. Fix the local-wheel timestamp rather than borrowing the caller's
ambient epoch. Keep failed working material in a bounded fresh destination;
do not recursively delete a computed temporary path. Preserve the existing
artifact's 512-member/six-change contract and fixed input/patch hashes.

No accepted source patch, existing committed tests, production pins, build,
staging, models, live library, port 5179 or paid API changes are allowed by this
repair. Run the worker's named suites plus the added boundary cases in both
roots around raw diff / three-way integration. Build in two fresh destinations,
compare bytes and independently verify every member again if the output changes.
Only then continue PACKAGE-09-INTEGRATION-BRIEF-2026-09-12.md.
