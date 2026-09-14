# Native04 copy inventory

The fixed inventory contains 86 payloads, 1,267,116 bytes: 40 files in the complete proposal04/history tree, 37 complete run files, 3 source-review files and 6 root records/verdicts. The largest payload is 309,037 bytes. Selected chains and members were checked for reparse points, every file was bounded to 1 MiB, and source size, write time and hash were rechecked after reading.

The retained observation passed generated writer exclusion and normal drain. Actual 0eeb20 and the controller/outer receipts record exit 0. Root's saved check records both exact children at exit 0 with empty jobs, three valid guards, four journal phases/flushes, 21 unchanged source controls and 14 unchanged support/fixture records. This inventory reconciled those saved records; it did not perform a new native observation or reopen support binaries.

Ordinary payloads are UTF-8 source/receipt text without NUL bytes. The only model.bin is the exact 60-byte generated ASCII fixture, SHA-256 e0a9fc9e76fc24578e81900fcb506dc23fa39c17dcb7313e83c382d731ed1f27. The only journal is the fixed generated 2,118-byte file ending fa6f2100000002000000000000000000.journal, SHA-256 02bca5b9c70324f1fe227bb111b9db36a93803a19ac79be873f38a21c4721867. Its hash agrees with the existing closed-journal receipt. Inventory access was opaque and supplies no new flush, exclusivity or recovery measurement.

The proposed copier must use only these rows, this directory's four files and its own reviewed source. Require a fresh proof folder, exact source membership, no reparse components, size/hash equality before copying, exclusive destination creation, and source/copy/after equality. Generate root * -text and SHA256.json after validation; retain any partial output on failure. These path checks assume quiescent files and do not claim race-proof handle protection.

Failed02/03 remain failed. Native04 does not independently measure a directory-size transition or establish power-loss behavior, restarted ownership, production namespace safety, real model execution, installation or release. The stable-directory archive and its inputs were left unchanged.
