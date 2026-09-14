# Documentary copy protocol

Do not execute during preparation. Once the final verdicts are present, freeze COPY-INVENTORY.json and its hash in copy_archive.ps1. Root reviews the final map and script before invocation. The target is fixed to docs/library/proof/runtime-owner-native-cancel-2026-09-13 and must be absent.

The copier reads only the map's fixed source paths plus its own source and map. Each row records the repository-relative source, archive-relative destination, exact byte count and SHA-256. The source roots are already scoped to text; no recursive run-directory selection or receipt-controlled file path is used. The five physical fixture files and registry directory are never inputs.

The copied map, copier and generated '* -text' attributes accompany the payload. Source bytes remain unchanged. All original inputs, the map and copier are reread after copying; every destination is checked against the original byte count and hash. The manifest contains all payloads except itself, and a final directory inventory must match that list plus SHA256.json exactly.

Root preserves the actual copy-tool outcome separately and performs any Git integration. This script does not run archived source, launch processes, verify support binaries or recreate any native observation. A failed copy leaves its partial target for diagnosis.
