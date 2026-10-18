# Static cycle diagnostic: training entry path observed

The diagnostic retains Reference cycle refused, reader and outer exit 2,
in 0.029370 seconds. It reports a five-node cycle reached along a known
training root. This identifies one observed path; shared references prevent
any claim that the cycle belongs exclusively to training metadata.

The witness is complete within its 12-node cap. Its path is newobj 2867,
dict 2868, list 2898, newobj 2901 and dict 2902. Recorded-operation edges
connect each symbolic object to its dictionary. A literal content-field
value leads into the list, and a literal parent-field value closes the cycle
to node 2867. No arbitrary field values or GLOBAL names were emitted.
These structural roles do not establish an OmegaConf class or semantics.

The unchanged reviewed reader is SHA-256
`15b9d339be34358dfecc2142a960cc524fe6e4620e0ec1716114027cac216ddd`.
It recorded the same 17,719,103-byte artifact digest and 131-member archive
before refusing. Normal final file-identity checks are not reached after
this refusal; no atomic or completed post-inspection stability is claimed.

Author and root synthetic runs each pass 36 cases with actual exit 0. The
23 inherited behavior checks stay unchanged, one composition predicate is
replaced by a scope-specific reporting-delta check, and 12 witness cases are
added. The original 24-case adapter qualification and its failed first attempt
remain historical evidence. This diagnostic did not relax cycle acceptance,
grammar, hash/ZIP/CRC checks or the 256-KiB final receipt cap.

Root read the full diff, all synthetic assertions and independent review
before this single new static run. The original 158-payload proposal seal
is preserved, with the exact reader, root brief/launcher, raw output and
actual refusal receipt. No model, object, tensor or converter ran; storage
members were not selected or decompressed. Opaque hash and ZIP-tail reads
retain their previously documented overlap with storage bytes.

The next design may inspect the existing selected metadata roots separately
while retaining the overall strict refusal and exit 2. It must independently
validate the selected reachable closure, refuse any selected cycle alias,
omit training values and label any returned static data partial and untrusted.
Source review and synthetic qualification are required before another static
invocation. No metadata, model, runtime or release approval follows here.
