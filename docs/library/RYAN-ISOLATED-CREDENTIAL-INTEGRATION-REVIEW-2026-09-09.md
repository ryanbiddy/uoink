# Isolated credentials: integrator verdict, 2026-09-09

Accepted with the documented integrator supplement. Isolated settings and key
operations now use the active validated profile. Reads cannot fall back to the
ordinary Uoink or legacy Yoink services; writes, plaintext migration and a 401
reset select the same isolated namespace. Normal-mode compatibility passes.

Gemini 4c02e121's original patch used 16 digest characters and substituted an
unresolved path after a resolution error. The integrated patch uses 32 digest
characters and refuses that alternate identity. Keeping settings on the same
active binding prevents a temporary isolated context from combining its key
namespace with an earlier settings path. No existing test file changed.

Independent original worker union: 117 passed / one expected failure, 13.86 s.
After the supplement, the same union has 117 passed / one expected failure in
the worker (13.75 s) and checkout (12.63 s). The expected failure is the existing
SEC-06 non-ASCII search case. These are focused observations, not a full-tree
pass or installed receipt. Both raw diffs, all worker observations and the three
independent runs are sealed in proof/ryan-isolated-credentials-2026-09-09.

The worker's report is retained as delivered. Its 16-character description is
superseded. Its claim that no key material is persisted is too broad: the new
migration test writes a synthetic dummy value into a temporary settings fixture.
The backend is a recording fake; no real credential is required or inspected.
The report also omitted a 103-pass/four-failure/one-xfail companion observation.
Those four mirror-output failures and every later run remain in the archive.
The worker did not supply a documented explanation for every intermediate rerun;
do not cite those retries as acceptance evidence. The independently reviewed
final diff and named union provide this integration's evidence.

This changes packaged server.py. The existing installer and ZIP remain older
observations; rebuild and reseal after the remaining dependency/instrument work.
No installer has run and no complete cybersecurity certification is claimed.
