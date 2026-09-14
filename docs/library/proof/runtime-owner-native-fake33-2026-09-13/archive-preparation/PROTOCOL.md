# Documentary copy protocol

Root should review COPY-INVENTORY.json and copy_archive.ps1 in full, then invoke the fixed copier once with the known PowerShell 7 host. No source or target arguments are accepted. The target must not exist.

Before creating the target, the script checks the exact inventory hash and every listed text input's byte count/hash, bounded regular-file properties and ordinary ancestors. It copies the fixed payloads plus its own source and inventory, writes * -text first, checks every source and destination again, and writes SHA256.json last. The manifest excludes itself and exact final membership is verified.

The root saves the actual outer tool result outside the sealed target. A nonzero exit remains failed even if output files exist. The script grants no admission and invokes no archived executable, qualifier, test, runtime or native function. Physical paths recorded inside JSON are data only.

The evidence preserves the author's 95-file preparation, the original sealed 18-file independent-copy preparation with its placeholder defect, root's repaired copy, and both distinct generated qualification receipts. The prior fake22 archive is guidance for copying, not an additional result included or repeated here. Git integration and independent disk/index verification remain root's next step.
