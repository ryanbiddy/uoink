2026-09-13. Accept the completed public-source collection and the fixed VAD
factory's source comparison. The reviewed constructor and strict-load calls
support the proposed 54-key state schema. This closes a source prerequisite;
native compatibility and model behavior remain unmeasured.

The collector passed the same 40 cases in its author and independent Astra
runs, with zero failures and all recorded exits zero. Those tests used fake
transport. The separately admitted resolve stage captured two HTTP 200
responses totaling 6,257 bytes. The source stage captured two API responses
and 19 fixed text files: 21 HTTP 200 responses and 1,050,728 bytes. Both stages
exited zero, retained unchanged input bindings and empty stderr, and resolved
the official v2.13.0 tag to cf30153c4c131c8164ee7798e5022d810682e2cb.
No model file, wheel or native library was retrieved or executed.

Astra read the comparison and repair brief, then checked the cited LSTM,
normalization, strict-load, backend and Windows-loader definitions. The LSTM
names and shapes agree with the 32 proposed entries; the complete proposal
still has 52 parameters and two buffers. Missing InstanceNorm metadata does
not add running-stat keys for the fixed track_running_stats=False route.
These are source findings, not an observed native state dictionary.

Before any separately authorized native trial:

- Set TORCH_DEVICE_BACKEND_AUTOLOAD=0 before the first Torch import. The default
  otherwise loads installed backend entrypoints; this also existed in 2.8.
- Resolve torch._native's import and registration scope. The flag above does
  not disable it, and its implementation was outside the 19-file collection.
- Bind the Windows import environment and loaded DLL locations. The target's
  NvToolsExt search is separate from its CUDA-version conditional; choosing CPU
  does not prevent that import-time setup.
- Verify the fresh process's trusted classes, load hooks, dispatch modes and
  default false swap/overwrite flags before strict assign=False loading.

The tag's version.txt literally says 2.13.0a0. It is not an installed-wheel
version measurement. Only init and RNN received direct paired 2.8 comparisons;
the other files were reviewed for the fixed calls. No whole-package equivalence
or signature attestation is claimed.

The 199-payload source proof retains the two synthetic runs, all 23 HTTP body
pairs, 12 old comparison inputs, source reports and documentary corrections.
Astra verified all 197 original-to-proof copies before copying the unchanged
200-file directory. Manifest SHA-256:
290a815003a3593d0685e5570c61feccf6884edada9dae80f5cc0887665b3a74.

The original timestamp strings are UTC. A derived PowerShell display caused
an erroneous unsealed draft claim; the draft and correction remain preserved.
Astra's first documentary copy verifier also exited 1: it counted three plan
files against the expected 48 timestamp receipt files. Fresh verifier 02
corrected only that selection and exited zero, checking all 119 literal UTC
strings. Both scripts, the reason and actual outcomes are retained separately.
No tests or HTTP collection reran for these reporting corrections.

Production remains e8d058f. Finish the real tensor bridge, ASR lifecycle and
owned runtime, then qualify a new committed tree and package. Website and
marketing remain paused pending council and integrator release approval.
