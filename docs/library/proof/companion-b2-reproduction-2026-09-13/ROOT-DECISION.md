# Private stdlib reproduction: root decision

On 2026-09-13, root read the complete copier/launcher, child and delta against
the first reviewed build, plus the exact 33-file plan and brief. Proceed under
the user's existing local repair/build authorization with the sealed copy
action, then the separate build action only if the copy receipt passes.

Bind preparation28 manifest
0b1cb98b296f34965d8bcebe8a67755bb5315df1a3663b479e282da630346f4c,
copier 6fcf3a4476b3b4517b227bf213a875c88831aa5a03e7435704362b8bca36ed26
and child 616295bae49ab05844a57e88ad1b47cc5b612cb9094e275c1aabcedd991a788a.
The original builder and four recipes remain unchanged. No additional
synthetic test count is claimed for these packaging wrappers.

Copy only the existing, hash-bound stdlib distribution into the fresh private
directory and write its exact no-site configuration. Do not launch or modify
the original embedded interpreter. Require all 34 private files to match before
launch, and the child's exact version, executable, two search paths and startup
flags before wheel access. The child verifies runtime bytes again, retains the
artifact guard, and compares its complete output with the first wheel after
building under a different ambient epoch.

This authorizes byte-only packaging reproduction, with no model/package import,
model interpretation, installation, download, test/pin edit or release approval.
Retain actual copy, child and outer exits and all failures. The paths must be
quiescent; local hash identity does not establish fresh publisher provenance or
atomic defense against a hostile process with the same user access.
