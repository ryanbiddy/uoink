# Whole-file wrapper deadline

Before qualification, retain the first unexecuted converter draft and add a cooperative deadline around the complete future real-file wrapper. The core already bounds hashing, ZIP validation, finite scans and output serialization, but its clock starts after a file snapshot has been read. The wrapper must check its own original clock after snapshotting, after conversion before any output creation, and after writing before returning a success receipt. Blocking filesystem calls cannot be preempted by this stdlib cooperative budget. If writing exceeds the deadline, the created file remains unaccepted and the call refuses; a later attempt must use a fresh output name.

The real profile stays absent, and no real file wrapper will execute in this task. A synthetic refusal test may call it only to prove that the missing-profile guard precedes all filesystem operations.
