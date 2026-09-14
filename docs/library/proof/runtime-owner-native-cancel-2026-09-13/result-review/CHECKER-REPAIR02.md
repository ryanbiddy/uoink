# Passive checker correction

The first tool composition failed at JavaScript parsing before writing or running a checker. No command or candidate ran from that tool call.

The first executed passive checker, check_receipts.ps1, then stopped at Reply binding (c7baa8, exit 1). It incorrectly compared serialized object insertion order for the controller/child policy and acknowledgement. Fixed-receipt diagnostic c4e4cb confirms that the flat scalar fields agree while their ordering differs. Its readback field_values_equal entry uses shallow array identity; the separately reported full JSON comparison for readback is true.

check_receipts02.ps1 keeps the first script and all other checks unchanged, replacing only that composite line with retained owner comparisons and exact key/type/value checks for the two flat maps. No subject source, acceptance assertion or observation was changed. Only passive receipt review is repeated.
