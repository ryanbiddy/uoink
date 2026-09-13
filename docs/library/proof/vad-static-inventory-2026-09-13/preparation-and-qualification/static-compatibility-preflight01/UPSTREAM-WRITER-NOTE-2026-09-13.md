# Bounded upstream writer corroboration

The PyTorch repository's bundled miniz source zeroes the central header and
writes needed version 0 for method 0. The short excerpt below was observed
on 2026-09-13 in the current upstream source, around the central-header writer.
It corroborates that this encoding exists; it does not identify which writer
or revision produced the staged artifact. [PyTorch's bundled miniz source](https://raw.githubusercontent.com/pytorch/pytorch/main/third_party/miniz-3.0.2/miniz.c)

```c
memset(pDst, 0, MZ_ZIP_CENTRAL_DIR_HEADER_SIZE);
MZ_WRITE_LE16(pDst + MZ_ZIP_CDH_VERSION_NEEDED_OFS, method ? 20 : 0);
```

This is a bounded text excerpt from a moving upstream branch, not a full
source capture or installed-version attestation. No upstream code was
executed. The proposed exception is narrower than the writer expression:
it also requires made version 0, disk 0, stored method, exact flags 2056 and
the previously observed whole-artifact hash. None of these facts establish
checkpoint architecture, tensor shape, conversion viability or loading safety.
