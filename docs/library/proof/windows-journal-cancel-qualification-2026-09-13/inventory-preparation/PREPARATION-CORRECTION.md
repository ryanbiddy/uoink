# Inventory preparation correction

The first data-only inventory command, actual tool 8672d7, exited 1 because two PowerShell object values used bare `false` instead of `$false`. It failed while constructing the inventory object, before creating the inventory directory or writing a map. No copy or qualification ran.

The corrected command uses `$false` for those two scope fields. Its source roots, exact single-file list, UTF-8 and size checks, and file hashing remain unchanged. The original 89-case author and independent results are unaffected. The complete actual tool object is retained beside this note.
