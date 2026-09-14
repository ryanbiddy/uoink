# Reused copier

The source baseline is _scratch/archive-native-retired-owner-recovery01-proposal01/copy_archive.ps1. Its exact bytes are selected as archive-preparation/before/copy_archive.ps1.

The new copier changes only the fixed preparation directory, archive target, inventory schema/hash and exact file/output counts. Its final relative-path normalization spells the existing one-character replacement explicitly as Replace([char]92,[char]47). The path, UTF-8, no-reparse, byte-bound, exclusive-write, before/copy/after, manifest and final membership logic is retained.

COPY-INVENTORY.json and the operative copier are added to the archive by the copier itself, avoiding a circular input hash. The inventory selects the brief, protocol, reference, reuse note, pending-selection history and actual inventory-preparation tool records. The generated top-level .gitattributes contains '* -text'. The resulting SHA256.json excludes only itself.

This is a documentary byte copy. It grants no authority to execute any archived checker or native source, and never visits the physical fixtures or journal.
