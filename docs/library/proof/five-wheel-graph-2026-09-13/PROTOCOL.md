# Documentary sealing protocol

Root must review the exact preparation manifest, sealer, verifier and source plan before invoking the sealer. No sealing or verification execution has occurred during preparation. The only static source check so far parsed the PowerShell files; it is not a runtime qualification.

The sealer accepts one preparation SHA-256 and creates fresh `_scratch/five-wheel-graph-proof01`. It refuses an existing target and changed source membership/hashes. It preserves every file in four named source roots plus ten standalone records. Four operative manifests contain 797 rows. Reused historical manifests and fixtures remain reconstructable through the hash-addressed payload mappings and the existing archive.

The external dependency is `docs/library/proof/runtime-candidate03-graph-2026-09-13`, committed at `4827288`: root SHA256.json `793a1c4826eabc278b795d0d2fbc06c642dfb2ca1cdf42d73cc4bb8e4fb941ec`, source plan `68c1a0927b3154788372026488b8332e4e66f6239736ee357a70eeab781a35e6`, and payloads.zip `8dba369e6f9063af80ca46c725a4e41e7d893dc7cb0b7c2324feab838a4175ed`. Do not present the new proof as self-contained without that archive.

The sealer hashes source bytes before and after copying, checks the four preparation manifests, reconciles both 68-case results and the full graph outcome, and writes a deterministic ZIP containing only 63 new unique payloads. Its timestamp is fixed, names are SHA-256 addresses, and no files are extracted or executed. Six key receipts are copied separately for review. The proof carries `* -text`, copy/source maps and an exact root manifest.

The independent verifier checks the new proof's exact file membership and all hashes. It checks the old archive's pinned bytes, exact new ZIP membership, the old ZIP's known member inventory, and the bytes of all 478 unique payloads referenced by the new source map. It closes all 797 operative preparation rows and binds the readable copies. It reads documentary ZIP entries only and never imports their source. The reviewed sealer/verifier themselves are the only scripts executed by this operation.

Bounds are 16 MiB per text member, 32 MiB for the external ZIP, and 128 MiB for the total referenced expanded payloads. Paths reject observed reparse points and non-directory ancestors. The operation assumes quiescent owned proof/scratch directories; it is not a race-proof filesystem lease or an OS sandbox.

After exact admission, use the observed PowerShell 7 host with the reviewed preparation hash. Save the actual outer tool object outside the operative manifest. On failure preserve partial output, do not delete it or rerun automatically, and prepare a separate repair brief. No test/graph, dependency resolution, network, package/model import, installation or native application run is authorized by sealing.

```powershell
& 'C:\Users\hello\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe' -NoProfile -File 'E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\five-wheel-graph-proof-proposal01\seal.ps1' -ExpectedPreparationSha256 '<exact admitted PREPARATION-HASHES.json SHA256>'
exit $global:LASTEXITCODE
```
