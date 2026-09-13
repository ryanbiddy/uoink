# Fixed two-wheel byte inspection — 2026-09-13

This is source preparation, not an invocation. Root may admit one inspection after reading the exact inspector, launcher, preparation manifest and eight retained provenance inputs. No synthetic qualification suite, dependency resolution, build or package execution is proposed.

The fixed inputs are the two cached wheel paths and historical size/SHA256 claims named in the inspector. Verify the whole-file pin before parsing ZIP structures. Refuse missing or changed files. Compare complete same-API path and handle identities before/after each read. On Windows, the cross-API comparison substitutes the required exact birthtime for ctime, preserving the already reviewed identity boundary without tolerance. Check path identity again after inspection and before the final receipt. Observed links/reparse points are refused. This is a quiescent-directory check, not a race-proof file lease.

ZIP inspection accepts only stored or deflated, unencrypted, regular files within the exact package and dist-info roots. Bounds are 1,000 members, 256 KiB per expanded member, and 8 MiB expanded per wheel. No comments, extra fields, directory entries, descriptors, gaps, overlaps or case-alias names are admitted. Local headers must match central fields and the payloads must end exactly at the central directory. `zipfile` checks CRCs while reading members. Every member is hashed against its exact RECORD row; RECORD's own row must have blank hash/size fields. All package payloads must be Python source, and native binaries or `.pth` files are refused. These bytes are hashed only: no member is imported, compiled, evaluated or extracted to a package directory.

The receipt records every member's name, size, CRC32, compression and SHA256. It embeds the exact UTF-8 METADATA, WHEEL, RECORD and any license/copying/NOTICE text under dist-info. Name, version, purelib and the `py3-none-any` tag must match. Missing license text is an explicit finding, not a fabricated notice or an automatic whole-product acceptance. Historical build/origin claims stay labeled historical; exact byte agreement does not authenticate a publisher or recreate the build.

The native interpreter is the already used `C:\Python314\python.exe -I -S -B`, with explicit lexical `IG_FORBIDDEN_LIVE` before startup, disabled backend autoload and scrubbed provider/proxy variables. Only stdlib inspection code executes. A small audit guard limits content reads to pinned preparation text and the two fixed wheels, writes to one fresh receipt, and blocks process/network/registry and filesystem mutations. The 30-second clock is cooperative. Inputs are at most 4 MiB; logs and the receipt are at most 256 KiB. No model/runtime module or the old Python 3.13 interpreter is imported or started.

After exact admission, use the observed PowerShell 7 executable once:

```powershell
$env:IG_FORBIDDEN_LIVE='C:\Users\hello\AppData\Local\Uoink\index.db'
& 'C:\Users\hello\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe' -NoProfile -File 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\two-sdist-wheel-repair-plan01\run_inspection01.ps1' -ExpectedPreparationSha256 '<exact admitted preparation hash>'
```

The launcher saves raw native exit immediately, before throwing postchecks, with PowerShell native-error promotion explicitly false. A valid complete byte inspection exits 0. A documented refusal exits 2 and retains any first-wheel result as partial evidence; it does not mark both inspected. Instrumentation failure has outer exit 99 while preserving the actual native result. Unexpected startup or serialization exceptions may leave only raw logs. Preserve all such outcomes and do not retry automatically.

Save the actual outer tool object outside the immutable preparation. After a valid result, root independently checks bytes/records and decides any graph-only admission change. This protocol does not install, rebuild, fetch or declare the runtime accepted.
