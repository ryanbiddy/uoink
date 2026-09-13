# Final serialization deadline repair before qualification

Independent review of source SHA256
`6defdb154a3d7bf9af1fa51b83cb111417f28f6877f01abe8a5082700acc3b85`
found that full receipt serialization could cross the original reader
deadline after the projection had been attached. The draft checked time
before serialization, so its serialized graph could survive that crossing.
Preserve this unexecuted draft in `draft01`; no qualification ran against it.

After full receipt serialization, check the original reader deadline again
before publication. If the result contains a partial selected projection
and time has expired, discard the entire projection, retain the original
strict cycle refusal/exit 2, and serialize a small fixed projection-refused
marker with reason original_reader_deadline_exceeded. The existing output
cap remains in force. Add a synthetic serialization/clock seam that crosses
the deadline during serialization and verifies that no projected node or
value survives. No artifact execution or bound expansion is introduced.
