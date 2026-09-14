# Before-open helper controls

The first fixture/test draft is preserved in draft01 with its actual copy result. The fixture is unchanged. The test now also replaces each fixed adapter helper and durable._require_factory_start after actual startup issuance but before factory entry. Every replacement is a refusal trap and must remain uncalled; no owner or factory attempt may be issued.

This follows the source reviewers' initial-entry finding: the first repaired factory could invoke a newly rebound capture function before checking its tuple. The source author is repairing that call site separately. Existing after-bind/after-finish controls remain. No case has run, and this preparation does not change accepted tests.
