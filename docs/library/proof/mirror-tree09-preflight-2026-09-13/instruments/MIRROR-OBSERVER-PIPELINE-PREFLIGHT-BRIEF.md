# Verify actual observer hooks with an inert failing case

The passive mirror plugin has 15 synthetic passes after its documented
incomplete-session correction. Astra will independently run those cases, then
activate both the existing partition receipt plugin and new passive plugin in
one guarded pytest process containing only two new scratch smoke cases.

One case passes. One deliberately fails after installing an inert module with
ordinary Python owner/session dictionaries. No product source is imported or
executed, and no process or mutex is started. Require the real pytest/verifier
exit to remain one with one pass and one failure. Require partition membership
and all six report phases, three observer captures, no observer errors, an
observer_finished record with pytest exit one, and preservation of the inert
identity map during the deliberate failure. This preflight grants no product
acceptance. Preserve all outputs and the deliberate failure as observed.
