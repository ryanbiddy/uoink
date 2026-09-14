# Documentary copy protocol

After root reviews the exact script and inventory, invoke copy_archive.ps1 once with the known PowerShell7 host, from E:\AI\projects\uoink\checkouts\Yoink-library. This is a text-copy operation, not a candidate qualification. The script takes no target or source arguments; the checkout, inventory and fresh archive destination are fixed.

The script first verifies the frozen inventory hash and every named source's exact byte count/hash. It validates strict UTF-8, bounded reads, ordinary file/ancestor paths and unique case-insensitive destinations. Only after complete input preflight does it create the archive, with * -text attributes. It copies the listed payloads and the exact map/script bytes using CreateNew, checks every archived byte, and rechecks every original input. It writes SHA256.json last, verifies exact final membership and every sealed hash, then prints scalar count/size/seal hash. No archived executable is launched and no metadata path mentioned inside JSON is followed.

The root must preserve the actual outer tool exit and output outside the sealed target. A nonzero process result stays nonzero even if some files were written. Preserve partial files for a separately documented diagnosis; do not rerun this copier over an existing target. Git staging and disk/index verification belong to root after successful independent review.

No test, native observation or result count is produced by this archive operation. Source and receipt claims remain those of the archived actual runs and reviews. All inputs must remain quiescent during copying; the checks are not an atomic snapshot guarantee.
