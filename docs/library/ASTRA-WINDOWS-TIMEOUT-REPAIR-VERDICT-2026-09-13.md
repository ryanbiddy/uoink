# Generated timeout cleanup: bounded result

The repaired pipe recognizes observed terminal broken-pipe failure after the exact operation event and nonblocking result query. It permits retiring that completed operation's buffer without treating the failed operation as cancellation or success. The ordinary release refusal and logical quarantine remain.

| Retained observation | Outcome | Elapsed |
|---|---|---:|
| Native timeout01, original pipe | Failed, controller/native outer exit 1; buffer retained and generated teardown refused | Controller 0.36601640001754276 s; outer 1.0279244 s |
| Author synthetic repaired pipe | 67 passed, 0 failed, 0 skipped; native/outer exit 0 | Cases 0.01925509999273345 s |
| Independent root synthetic | Same 67 complete ordered case results; native/outer exit 0 | Cases 0.01809460000367835 s |
| Native timeout02, repaired pipe | Generated terminal retirement/teardown qualified; controller/native outer exit 0 | Controller 0.3549365999933798 s; outer 0.9977747 s |

Both native cases observed the intended missing-response failure: requested event wait 250 ms returned WAIT_TIMEOUT 258, the exact owned job was stopped, and retained process queries found child exit 1 and an empty job. CancelIoEx returned 0/1168, then the operation event signalled and GetOverlappedResult returned 0/109. The old helper retained the buffer; the repaired helper retired it. In timeout02 the response/cleanup interval was 0.25525389998801984 s; this is an observation, not a fixed latency guarantee.

Timeout02 kept the original parent guard through process/job observation, refused ordinary read-set release, and closed the disposable generated handles only with zero pending I/O. A subsequent write-access open succeeded without writing. Its state remains QUARANTINED (7), `read_set_released=false`, `quarantine_persisted=false`, and `pipe_retired=false`. Those logical fields are intentionally not rewritten by the generated physical teardown. The child record is a pre-stall snapshot, not a final success receipt. Its actual exit 1 came from the controller's retained process query.

The original 54-case source remains byte-identical at 419d9c10f03ee80167567f2332b70d1153f1e940ebf50269070d84aa7c7b5071. Thirteen added controls exercise 109/995/success distinctions, incomplete/unknown/invalid-handle refusal, exact wait/result identities, cancellation-request failure, interruption and failed event closure. Both raw lists have 67 unique cases and identical complete case rows. The fixed repaired pipe hash is 73a1109a55f2bc807594655c71b24a3e35eb88d7f744497df2cc328dc224cae7.

The native runs retained valid guards with 134 and 142 matching dispatch/audit events respectively. Both bound six source files, three controls and nine installed-support records before/after. The second launcher had a five-file draft copy-list defect found before native execution; the correction and prior draft are preserved. It did not alter the pipe or synthetic assertions, and no failed native launch is invented for that draft.

This result covers one controlled generated-worker timeout and its terminal I/O cleanup. It does not implement durable quarantine recovery, clear a production read-set, reconstruct a real child model namespace, run a model/decoder, qualify native runtime imports generally, or establish installed/release/market readiness. Immediate process exit protected pending native buffers on the failed first case; failed receipt construction variants were source-reviewed, not separately fault-injected here.

Astra accepts this repair for the generated scope. Root documentary builder
8aa5a4 and verifier 7b4907 both return zero; index check 5f574a verifies all
117 timeout and three integrator payloads against Git and disk. The main
proof contains 986,692 bytes and maps 184 original text files to 108 distinct
objects. Its original MANIFEST.json is copied byte-for-byte as SHA256.json:
25ff14f8ee5b75a65caa3d711f8f22ee171dabd510454441a5b39f26797c895d.
No archived source or test ran during verification. The standalone actual
builder/verifier results are preserved in the three-payload integrator proof.

Positive and refused inherited-file observations are the next integration
unit. The product runtime, durable recovery, complete tree, current package
and installed receipts remain open. Website and marketing stay paused.
