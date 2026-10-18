# Five local wheel records — Astra graph review

2026-09-13. The revised metadata checker and complete retained dependency graph pass. This closes the preceding graph's two wheel-evidence gaps. It does not establish native compatibility or release security.

| Measurement | Actual tool | Pass / fail / error / skip / subtest | Outcome |
| --- | --- | --- | --- |
| Author qualification | `468c4b` | 68 / 0 / 0 / 0 / 0 | Valid guards; native and outer exit 0 |
| Independent qualification | `36df84` | 68 / 0 / 0 / 0 / 0 | Same ordered observations; native and outer exit 0 |
| Complete graph | `e8f43c` | Graph result, not a test count | PASS; 144 pins, 287 active edges; native and outer exit 0 |

The checker adds exact local records for the inspected ANTLR and proxy-tools wheels. Its original 36 public cases remain unchanged. Both qualifications preserve all 367 input records. The complete graph has empty missing-package, constraint-conflict, wheel-failure, incomplete-evidence, manifest, marker, direct-URL and selection-error lists. Its 313 captures, 47 preparation inputs and observed file identities remain unchanged. Driver time was 3.4340338000038173 seconds; actual outer wall time was 3.9960709 seconds.

All five local wheel entries retain null public URLs, `public_release_record=false` and `artifact_verified_in_this_invocation=false`. ANTLR and proxy-tools retain absent `Requires-Python` values. This checker reads retained metadata; separate byte inspection supplies wheel evidence. No wheel was installed or imported in these graph runs. The fixed target is Windows CPython 3.13.15; the host executing this metadata calculation was Python 3.14.6.

Astra reviewed the source deltas, both qualifications, the complete graph driver and final result. The prior invalid 51/11 qualification and prior valid three-record graph FAIL remain unchanged in `4827288`'s archive. Current preparation errors are preserved as preparation outcomes; none is counted as a graph run. The proxy-tools source/metadata license conflict remains explicit in the separate notice verdict at `d887f8a`.

After reviewing the sealer and verifier, Astra ran documentary operation `6b3ee1`: exit 0, 9.9606451 seconds. It copied and verified saved bytes without repeating any test or graph. The 22-payload proof maps 1,050 source paths and all 797 operative preparation rows. It stores 63 new text objects in a 408,968-byte ZIP and references 415 existing objects in the required archive at `proof/runtime-candidate03-graph-2026-09-13` (`4827288`). The proof is not self-contained without that archive. Its seal is `080551135a2d18de7217a39acf5e3c444efeaa5a662136eb9c52b9fed75cb617`. The separate integrator proof retains the actual documentary result.

Evidence: `proof/five-wheel-graph-2026-09-13` and `proof/five-wheel-graph-integrator-2026-09-13`. The embedded verdict and mappings retain exact timings, sources and receipts. Real runtime, loader/session connection, crash recovery, models and final installation remain open. Website and marketing remain paused.
