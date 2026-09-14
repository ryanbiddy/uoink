# Documentary-only invocation

Root should read the exact COPY-INVENTORY.json and copy_archive.ps1, then invoke the script once with the known PowerShell7 host from E:\AI\projects\uoink\checkouts\Yoink-library. The script takes no arguments and fixes both checkout and fresh archive destination. It imports or launches none of the archived code.

The inventory enumerates every proposed source, control, receipt and review payload. The copier also retains the exact inventory and its own script, adds * -text attributes, and writes SHA256.json last. Bounded reads verify strict UTF-8, file/ancestor shape, stable observed metadata and SHA-256. CreateNew writes prevent overwriting existing files. Source checks occur before and after copying; final checks cover every sealed byte and exact membership.

No physical fixture, registry/journal, support path, model/checkpoint or converted output is opened or statted. Recorded native and generated-file identity fields remain unmodified JSON data. The closed-journal receipt and controller's generated hex are preserved as evidence; no new journal read is needed.

Save the actual outer tool result outside the sealed archive. A nonzero exit is never relabeled because some payloads were written. Preserve partial evidence and diagnose separately; do not rerun over an existing target. Root handles independent verification and any Git operation afterward. This operation produces documentary counts and hashes, not new test/native qualification credit.
