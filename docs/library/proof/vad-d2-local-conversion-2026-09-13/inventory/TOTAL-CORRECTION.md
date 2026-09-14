# Inventory total correction

The first data-only inventory command (9c4f84, exit 0) captured all 54 source rows and correct per-group totals, but Measure-Object did not resolve the bytes member of the in-memory ordered dictionaries. It wrote null overall total and maximum fields. That draft is not an accepted inventory.

Preserve its exact map and actual tool object. Correct only the two aggregate fields with explicit integer accumulation over the already captured rows, assert the 54-member count and 223,710-byte total, then retain a separate correction result. Source rows, hashes, receipts and conversion outcome remain unchanged. This is documentary preparation; no candidate or archive copier is executed and no checkpoint/output is accessed.
