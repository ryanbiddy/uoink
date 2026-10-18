# Child namespace01 source review — 2026-09-14

**FAIL. Do not admit this delivery for execution or integrate it as working
source.** Control Room run `05a3bf93-0b6c-47f0-bdd3-80b14e46b1d3` completed
with outer `7481e5/0`; that is provider completion, not product acceptance.
All 17 proposed tests remain unexecuted. Production remains `71d3e70`.

Freeze `47c823/0` retains all 26 delivered texts, 553,800 bytes, under
`_scratch/real-child-namespace01-root-review/frozen`. The pin map is
`75d20134558f5cebf61a8dc219d8652bf9d592a1ca29d835d757c8fd749fa124`.
Root `14eaa9/0` verifies every frozen file, seven derivative rows, eleven
original/copy pairs, 25 worker hash rows and all 17 declared test IDs. These
byte checks do not change the source verdict.

1. The controller flow imports nonexistent `AdapterRefusal`, treats the returned
   `_ControllerASRStart` as a token with `.token`, and mismatches the stage and
   envelope function signatures. It attaches a suspended worker but never uses
   the actual durable bind/resume/publication sequence. Assigning `record.worker`
   does not populate `session._worker`. It also reads a nonexistent manifest
   digest key and offers a zero namespace digest fallback.
2. The stage validator accepts incompatible phase pairs and makes worker checks
   optional. The coordinator accepts independent effectful configuration and
   reaches process effects before its intended validation. It does not establish
   fixed controller issuance, source or transport authority.
3. The child path calls the adoption method with the wrong arguments, passes
   a string where an adoption receipt is required, and calls nonexistent
   `mark_begin_accepted`. Adoption itself permits materialization without an
   accepted begin. Its directory identity conversion expects a `FileIdentity`,
   while the actual admission carries a tuple.
4. Namespace issuance requests an owner-operation phase absent from the fixed
   owner contract and expects `status`/`buffers` attributes absent from the
   actual namespace. Shaped objects and a mutable lease cannot replace exact
   adoption, namespace and owner issuance bindings. Unread cancellation also
   bypasses the confirmed read-set release path and can label aggregate
   uncertainty as released. Materialization needs a retained owner attempt.
5. The proposed fixture fabricates startup, session, permit and manager objects
   instead of using accepted issuance. Its model schema invents different
   repositories and filenames. Positive tests cannot traverse the actual
   contracts, and no test calls the imported controller or child coordinator.
   Control16 can finish without proving a cleanup failure or any raised error.

Root read the complete fixture/tests (`640f5d`, `f4ff4d`), coordinator and adapter
addition (`45192c`), and complete adoption addition (`850ee1`). Independent
controller verdict `b63b1523` agrees; passive `897548/0` reconstructs its entire
adapter diff both ways. Process verdict `e8604af5` and passive `a6c0ab/0` verify
the child findings and all three other full diffs. Root read the complete peer
verdicts (`3bb572`, `b20252`). Root's earlier suspicion about `GenerationChannel`
positional arguments was withdrawn: three positional arguments are correct.

The final outer output is retained truncated. The separate original database
export retains 1,042 events. Fourteen records cover seven command steps; several
parameters are shortened previews. Root `0a76c5` reads those original records;
complete command coverage remains unverified. Do not reconstruct missing text
or adopt the worker's broad execution/provenance claims.

Two root preparation mistakes are preserved without changing any subject
result. Search `5ba9d0` named a nonexistent lifecycle filename; subsequent
inventory `90a41e` located the actual source. Its tool-history record was not
separately saved or reconstructed. Notes staging `798ce0/1` stopped before a
write because the clean worker used CRLF. Diagnosis `d1e7d0/0` proved only
newline differences; separate helper02 and repair note led to `68f856/0`.

Follow `CONTROLLER-WORKER-STAGE-REPAIR-BRIEF-2026-09-14.md` for a fresh stage-only
derivative from accepted `6482b782`. Preserve this failed source and its tests.
Startup81 and generated39 remain accepted only within their existing scopes.
No D1/D2 repeat, runtime, full-tree, package, installed-client, website or
marketing clearance follows.
