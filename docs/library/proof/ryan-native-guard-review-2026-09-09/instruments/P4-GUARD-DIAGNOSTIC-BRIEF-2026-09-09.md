# P4 audit-hook diagnostic, 2026-09-09

Gemini, work independently in your assigned worktree. Read
E:\AI\projects\uoink\checkouts\Yoink-library\docs\library\RYAN-FINAL-MEDIA-REPAIR-BRIEF-2026-09-09.md
and the complete raw failed trace in
E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\ryan-security-final-tree-02\tests.log.
Write docs/library/GEMINI-P4-GUARD-DIAGNOSTIC-2026-09-09.md early. No subagents,
commit, installation, original helper outside named tests, paid API, credential
store query, model/media download, live index or port 5179. Do not edit existing
tests or product code in this diagnostic. You may add ignored scratch diagnostics.

Identify exactly how the P4 audit hook is installed into the shared pytest parent,
which earlier test caused it, and the smallest honest repair with no guard
weakening. The hook path in the recorded failure is
_scratch/ryan-security-final-tree-02-0/t291/r/p/guard/sitecustomize.py. Inspect the
source and relevant tests; do not assume subprocess child guards should leak.
If needed, add a diagnostic wrapper around sys.addaudithook that records the
installing stack and current pytest node and always delegates to the original
sys.addaudithook. Never block or remove an installed guard. Observe only the
minimal relevant P4 tests followed by the original media case, using the main
checkout's guarded _scratch/integrator_verify.py and private native interpreter
_scratch/ig-native/Scripts/python.exe. Set IG_FORBIDDEN_LIVE only to the forbidden
path string, never access it. Strip every paid API key. Use fresh labels.

The reviewed LGPL ffmpeg/ffprobe already exist at the main checkout's
_scratch/final-native-bin-01; append that directory only to this diagnostic PATH.
The long test also requires libx264, absent from LGPL; report that separate
prerequisite rather than weakening its assertion. The short test uses ffv1.
Do not copy or edit the binaries. A refused ffmpeg spawn is expected evidence
for diagnosis, not a successful media test. Report exact source paths, cause,
diagnostic commands/exits and a recommended narrow repair. Astra integrates and
independently verifies any resulting fix under a subsequent bounded brief.
