# Proposed inert qualification — not run

Root reviews the exact source, recipe and external-port contracts first. No
actual artifact, package import or model execution is part of these proposed
checks. A later brief must define source-only AST or inert-module seams and
guard the process before any qualification is admitted.

- Verify every before-file against retained release-tree blob ID/size and every
  recipe member against exact after bytes. Assert the full member set and
  exclusions, both TorchCodec declarations and the distinct local version.
- With the real port None, public load and direct ASR/audio/Pyannote module
  entry must refuse before heavy-import sentinels. Optional modules and public
  alignment/speaker/file APIs must refuse even with an inert active port.
- With inert owned ports, verify missing/wrong VAD, model name/relative path,
  local_files_only=False/1, credentials, download root, supplied model and VAD
  selectors cause no ASR constructor call. A refusing load-parameter check must
  precede construction for GPU/default compute, index, threads, task, language
  and altered option inputs. Exactly accepted parameters reach the fake
  constructor unchanged; no fallback runs after a constructor failure.
- Through inert array seams, reject subclass, wrong dtype/endian, dimensions,
  noncontiguous, empty, oversized and nonfinite input before native operations.
  Preserve a valid waveform unchanged; assert the owned decoder binding receives
  16000. A finite array without a matching owned waveform receipt must refuse.
- The VAD constructor must reject string/path/dict/None before its fake parent
  loader. An exact owned model reaches only the Model-instance path. No
  checkpoint-selected import, legacy loader or Hub callback may execute.
- Verify both filter shapes, dtype, finiteness and absent/malformed-port
  refusal with no NPZ/open fallback or global tensor cache. Preserve the
  generator call shape and initializer bypass in a new bounded inert test;
  do not reuse earlier counts as results for this patch.

Any later real-use protocol must additionally test session-bound object
identity, stale-reference refusal, concurrent mutation, constructor failure,
cleanup/quarantine and native reopen under actual protected snapshots. The
source-only port does not supply that boundary. Build qualification and runtime
qualification are separate; neither changes the current owner gates.
