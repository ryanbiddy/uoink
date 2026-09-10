# Native FFmpeg pin repair, 2026-09-09

Gemini: work only in your assigned worktree. No subagents or commit. Read the
handoff Standing rules and NATIVE-BINARY-SECURITY-BRIEF-2026-09-09.md. Your earlier
native review is at the main checkout's docs/library path after integration,
or in worktree a8752e4f-c54/gemini. Its conclusions need Astra's corrections:
it miscounts package inputs and mistakes a prerequisite for the observed failure.

Repair only the shipping FFmpeg pin in build.ps1 and its current build/version
documentation. Select the retained monthly LGPL 8.1.2 build:
https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-08-31-13-27/ffmpeg-n8.1.2-50-g1a748fe2cd-win64-lgpl-8.1.zip
SHA256 f6274bbd9c247f9e90c1bbed066b03ed4a3907cece2fb91be6dd352393936365.
Independently verify release metadata and checksum before setting the pin. Use
a versioned cache filename so no old archive is deleted as a hash mismatch.
Do not ship GPL; do not change Python or any package lock. Astra handles native
downloads, Defender scans, binary execution, actual media verification and build.

Do not edit existing tests or fixtures. Identify and run the existing build,
lock and documentation suites that cover this change with the main checkout's
_scratch/integrator_verify.py under _scratch/ig-native/Scripts/python.exe.
Set IG_FORBIDDEN_LIVE to the prohibited path string before that interpreter
starts; never inspect the prohibited file. Strip paid API keys. No live index,
5179, model or media fetch, paid API, credential access, installation or build.
Record all commands/exits including failures and exact diff in
docs/library/GEMINI-FFMPEG-PIN-REPAIR-2026-09-09.md. Name the suites for Astra
to repeat in both roots. Write the report early and finish a bounded change.
