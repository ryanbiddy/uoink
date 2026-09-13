# Reader and synthetic setup repair before static-preflight02

`static-preflight01` completed with 31 passed and 2 failed; the real process
exit was 1. Its source, setup, stdout, stderr and exit receipt remain unchanged.
No actual checkpoint was opened.

The backslash-name case was not testing its intended bytes: Windows ZipFile
normalized the name while creating the synthetic container. The corrected
setup changes the local and central filename bytes after container creation.
The behavior assertion still requires the unsafe name to be refused.

The underreported-deflate case exposed a reader defect. ZipFile can return
only the declared uncompressed prefix of a longer deflate stream; a matching
forged prefix CRC then hides the rest. The reader will read only the bounded
compressed `data.pkl` bytes from the existing stream and use stdlib zlib with
an output cap of the declared length plus one. It must require exact size,
completed deflate stream, no unused or unconsumed compressed bytes, and CRC
agreement before opcode parsing. Stored pickle data gets exact-size and CRC
checks too. This does not decompress storage members or execute a pickle.

Manual review also found that the advertised directory count was checked
before ZipFile, but the actual count was checked only after ZipFile allocated
its entries. The reader will scan the already bounded central-directory bytes
first and refuse extra/truncated/unsupported entries before that allocation.
Fresh synthetic cases will cover the pre-allocation count boundary and stored
payload size/CRC refusals. All existing behavior assertions remain unchanged.

The reader remains a proposal for static metadata only. The first attempt is
failed, regardless of later corrected results. This brief exists before edits
and before the fresh synthetic run.
