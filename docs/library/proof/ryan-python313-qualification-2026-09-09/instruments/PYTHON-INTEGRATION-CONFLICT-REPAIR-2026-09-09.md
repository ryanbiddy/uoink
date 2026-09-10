# Python integration conflict correction

The three-way Python patch conflicts with the already integrated FFmpeg update
where adjacent hashes and documentation rows share a hunk. Preserve the raw
conflicted diff. Resolve by retaining Python 3.13.15 and its official SHA256,
plus the existing monthly LGPL FFmpeg 8.1.2 URL, hash and cache filename.

The launcher incorrectly continued to run astra-python313-c1 before resolving
the conflict. Its 36 passing static tests in 1.97 seconds are not acceptance of
an executable build script: conflict markers were still present. Preserve that
observation and do not report it as the integrated verdict. After resolution,
require zero unmerged paths and a real PowerShell parser check, then repeat the
seven named suites as astra-python313-c2. No acceptance test changes.
