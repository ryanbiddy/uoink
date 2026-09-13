# Python 3.13 follow-on proposal — 2026-09-13

This step is separate from the prepared Python 3.14 first build. No private
runtime has been copied or launched. The exact 33 retained top-level inputs,
sizes and local SHA-256 identities are in `python313-runtime-copy-plan.json`.
They contain the embedded Python distribution's binaries and stdlib, with no
third-party package directories. The proposed destination is fresh scratch
`b2-stdlib313-runtime01`; its new `python313._pth` must contain exactly the
16 bytes preserved in `python313-private-pth.txt`, without `import site`.

The historical graph version probe reports Python 3.13.15. The NLTK wheel
receipt used the staging interpreter with `-I -S -B` and recorded matching
wheel bytes, but did not record startup flags or the absence of `site`.
The current retained graph and staging `_pth` files contain `import site`.
Those facts do not establish safe startup for another invocation. Neither
original configuration will be modified, and neither original interpreter
should be launched for this work.

After review, a stdlib Python 3.14 copy utility would require a fresh destination,
reject links/reparse paths, read each listed source within its exact size plus
one byte, compare before/after handle and path identity, and verify the exact
hash before writing. It would copy only the 33 listed files, write the private
configuration, and verify the complete destination set and bytes. It would not
run the copied interpreter. The source paths must be quiescent; these checks
detect observed changes and do not defeat every concurrent same-user mutation.

A separately reviewed child could then inspect its own startup under `-I -S -B`
before accessing a wheel. Required results: Python 3.13.15; isolated, no-site
and no-bytecode flags set; `site` absent; `sys.path` confined to the private
directory and its stdlib ZIP. Only then could the same reviewed builder and
recipe run under the artifact guard, using a different output root and epoch.
Compare its wheel bytes with the real Python 3.14 result. The copy utility,
startup receipt, second build and comparison are all pending.

This inventory binds existing local bytes. It does not establish new publisher
provenance or accept any model stack, installation or release.
