# One local conversion for Ryan's decision

The source is ready for an owner decision. Astra and the independent reviewer found no remaining material source blocker. Both copies pass the same 23 generated adapter cases. Those tests do not establish actual conversion success or filesystem-wrapper behavior.

The proposed operation reads the existing 17,719,103-byte checkpoint once, verifies its exact hash and ZIP contents, and writes one fresh Safetensors file containing 54 fixed tensor ranges from 23 selected storages. The dense tensor data is 5,891,996 bytes; total output is capped at 6 MiB. The destination is `_scratch/vad-fixed-converter-approved-output/default-vad-d2-01.safetensors`. It will not overwrite or retry an existing output.

Approval must accept these four limits:

- The selected storages are assumed to share a uniform raw-storage writer. D1 checked two buffers; it did not authenticate the writer or validate every storage's meaning.
- Values use little-endian IEEE754 binary32 interpretation. The converter checks the selected lengths and finite encodings.
- The output stores the 54 reviewed ranges densely and omits legacy checkpoint metadata.
- Conversion is local only while the complete model notice remains unresolved. There is no redistribution approval.

The converter does not evaluate pickle, instantiate a tensor/model runtime, run inference or fetch data. It does not activate the real plain-state reader. The new output remains unqualified for model or release use. D1's completed inspection is not repeated.

The reviewed parent/child uses fixed private paths, source and authority hashes, an exclusive output create, audit and registry guards, a cooperative 30-second converter limit and a proposed 60-second parent timeout. These controls are not an OS sandbox or proof of race-free path access. Failure, partial output, timeout or invalid receipts remain failed and are preserved.

The exact proposed profile SHA-256 is f0c60e2fa349b945108b4d15dccc8fe2d68ca4cab8588e8c0ff7f2e8762f75d3. The checkpoint SHA-256 is 0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea. The owner record currently remains a false template, and the three real source pins remain None. Only Ryan's separate D2 decision may enable a new exact root admission. D3 fetching, D4 native execution, installation and publication remain separate.
