# Generated Windows worker verdict — 2026-09-13

Native04 passes one real Windows observation of the owned worker's positive
path. Astra accepts that result and its independently reviewed source. This
does not qualify model execution, timeout cleanup or the release.

A suspended stdlib-only child receives the private pipe and generated file
handle through the explicit inherited-handle list. The controller assigns the
child to its owned job before resuming it. The actual lifecycle and handshake
carry a 40,000-character generated payload with the expected digest. The parent
then closes its original file handle; temporary inheritable copies are already
closed. The exact child remains alive, and a write-access open is refused with
Windows error 32 while the child alone holds the file guard.

After the cancel/closed exchange, the controller observes the retained child
process exit with code zero and the owned job's active-process count reach zero.
Only then does it finish the normal release path. A write-access open succeeds
without writing bytes. The fixture remains its original 64 bytes. A wire reply
alone is not credited as process exit or safe release.

Actual tool 7b331c returns zero in 0.724325 seconds. Controller and child report
0.10295770000084303 and 0.01320839999243617 seconds. Controller/native/outer and
child exits are zero. Both roles have 31 fixed function bindings; controller
records 148 dispatch calls and matching audit events, child 109. Both retain
12 metadata traps, 25 registry wrappers, zero invalid dispatch contexts, zero
guard denials and zero model imports/calls. Output and error logs are empty.

Root a58725 independently checks the six source files, three original/copied
controls, nine installed Python/ctypes/System32 support inputs, actual result
records and generated fixture. Their hashes match the before/after records.
The installed inputs are quiescent-file observations; this is not exhaustive
DLL verification or a Windows security boundary against arbitrary native code.
The initial ctypes load of kernel32 and subsequent exact System32 load are
both recorded and verified as the same module handle.

The three preceding attempts remain failures, all before child creation:

| Attempt | Actual result | Diagnosed repair |
|---|---|---|
| native01 / 84f5c9 | Native/outer 1; 495-byte traceback | Bind the exact installed lazy ctypes layout source and preload warnings. The raw import refusal lacks an import name; the layout diagnosis comes from source inspection. |
| native02 / 04414f | Native/outer 1; 498-byte traceback | Admit only fixed, same-thread ctypes dispatch contexts and exact pointer/argument bindings. |
| native03 / 08be19 | Native/outer 1; 316-byte traceback | Correct the mistaken instrumentation count of 32 to the source-derived exact set of 31. API scope and flow assertions remain unchanged. |

Earlier source reviews also accepted the mistaken count; that claim is withdrawn.
These were failed native setup observations, not claims that no native library
had loaded. Each fresh attempt has its own brief, exact controls, actual result,
original source and diff. No failure was overwritten or relabeled.

The combined proof in `proof/generated-windows-worker-2026-09-13` retains 169
logical files as 111 content objects and 119 sealed payloads, totaling 722,172
bytes. Builder d8dcd7 and separate verifier b76fbf exit zero without executing
archived programs or repeating the Windows observation. The original manifest
is renamed SHA256.json on repository copy without changing its bytes; seal:
72e2fb40f0ba2292cc5c9bc33c1a9278f8ba4cf15a844de2ebad0d54006290d8.
Separate integrator records retain both actual documentary tool results.

The child does not reconstruct model read sets or use the real factory, decoder
or native ML stack. Timeout, forced stop, cancellation uncertainty, cleanup
reserve and controller crash recovery remain unmeasured. The next bounded
generated-worker check targets nonresponse and forced stop; eight separate
handshake contracts add negative ownership/phase coverage. Production remains
e8d058f. The current installer, complete runtime and market release still need
validation and council approval. Website and marketing remain paused.
