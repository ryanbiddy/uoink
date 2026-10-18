# Controller handshake verdict — 2026-09-13

Author and independent Astra runs each pass the same eight handshake cases,
with zero failures or skips. The actual lifecycle and protocol enforce the
reserved/ready/running/begin order and refuse a foreign permit, unregistered
worker, wrong phase, substituted record, repeated ready message and use after
session closure. Refused operations preserve the expected frame sequence.

These cases use fake process ports. They add negative protocol coverage to
the real Windows positive observation at 668b08a, without claiming new kernel
shutdown or model-runtime evidence. The lifecycle and protocol source remain
a80514aa and 78c395da; the eight case bodies and all earlier assertions are
unchanged between observations.

The author run, actual tool 00f8b6, takes 0.0011653999972622842 seconds inside
the harness; the independent run, d16104, takes 0.0012442000152077526 seconds.
Both native/outer exits are zero. The same eight ordered case records match;
12 metadata traps and 25 registry wrappers remain intact, with no denials,
heavy imports or captured output. Both actual stderr files are empty.

Before first execution, peer review found that the launcher's admission file
was copied without before/after hash checks. Proposal02 adds that control to
the existing copy checks; it changes no case or product source. Both runs now
verify seven source/control inputs. The independent launcher's only source
change is its literal proposal directory. Original preparation, false template,
control repair, admissions, copies and actual tool records are preserved.

The 71-payload proof in `proof/controller-handshake-2026-09-13` contains 409,294
bytes. Root documentary check/sealer 1e5ad0 returns zero after checking exact
case membership, guards, raw exits, seven input hashes in each root and the
single directory substitution. It executes no archived code or tests. Seal:
3ec265d93e7b7ecbaf4fae73165ddf4ff84bf9eda70b500ec5c0aa7d921ae971.

Timeout/forced-stop and child read-set adoption are the next real Windows
checks. Model execution, current-source installation and release approval
remain open. Website and marketing remain paused.
