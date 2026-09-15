# Package-07 delivery preflight corrections

Two documentary preparation checks exited one. No product test, installer,
client or ZIP builder was running in either check.

The delivery-script adapter completed four outputs, then refused the final
sealer adaptation because replacing review_bundle06.py had already changed that
substring inside seal_review_bundle06.py. Keep the partial preparation and all
completed outputs. Generate only the missing sealer from its retained original,
replacing longer names first; do not replay the whole preparer.

The staging check added the reviewed files, then refused Git's quoted ignored
paths. Its line-based parser did not decode Git's quoting for paths with spaces.
Retain the original check. A separate check02 uses git check-ignore -z with
NUL-delimited input/output. It still requires every returned path to occur in
the verified seal, force-adds only those exact paths and compares every staged
blob against the seal. Do not alter global or repository ignore rules.

Astra reviewed these causes and bounded corrections. Preserve both tool-returned
diagnostics, original scripts and diffs. Neither correction changes a measured
status or source payload. Continue to the clean documentary commit and build
the review kit once, then verify all ZIP/extracted hashes and portable paths.
