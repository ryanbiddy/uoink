# Final media execution repair brief, 2026-09-09

The committed full tree at 7109182 has 2,484 passes, three failures, two skips
and one xfail in 1,568.94 seconds. Preserve it as FAIL. AT6 is the original
missing exit record. Both new failures stop before FFmpeg executes:
tests/test_long_video_v324.py::test_screenshot_phase_end_to_end and
tests/test_screenshot_extraction_cm10.py::test_limited_range_15_second_fixture_produces_eight_jpegs.
Their traceback raises PermissionError from a P4 sitecustomize guard under
the prior test's t291/r/p/guard directory. The newly available FFmpeg exposes
this process-scope conflict; it is not evidence that either decoder operation ran.

Astra initially suspected the separate libx264 prerequisite. Source inspection
confirms that the long-video generator requires that encoder and the shipping
LGPL build omits it, but this is not the actual failure in the recorded tree.
The old long-video test returned early without pytest.skip when FFmpeg was absent;
its historical passed status does not prove that its media body ran. The short
test previously reported a real skip. Preserve those distinctions.

Diagnose the parent-process guard activation and repair the execution conditions
without editing any existing fixture, assertion or skip. Never weaken the P4
guard, remove an audit hook, suppress the exceptions, or return a fake successful
process result. Prefer a product/instrument lifecycle repair when the evidence
supports one. If the conflict is intrinsic to irreversible audit hooks in the
combined process, a reviewed full-tree process partition may isolate those tests;
every original test must still run exactly once, with a complete node-id union,
no missing/duplicate case, raw per-process results and a clearly labeled aggregate.
Only S21 may remain absent across that union. Do not silently change ordering to
avoid a failing assertion or label a partitioned run as one monolithic process.

Separately provide a hash-verified private GPL FFmpeg test tool for the existing
libx264 generator. It is not part of the shipping LGPL package. Verify original
media cases with that test tool and separately exercise the actual bundled
decoder on synthetic inputs. No external source media, model, diarization,
credentials, paid API, ordinary index or port 5179 is authorized.

The binary-version review also found that the January 2025 FFmpeg pin predates
later documented upstream security fixes. Gemini reviews native FFmpeg and Python
under NATIVE-BINARY-SECURITY-BRIEF-2026-09-09.md. Review any compatible native
dependency repair before the next package build. Preserve package-04 and its
prepared, uninstalled receipt. Any changed compiler input needs a fresh package
seal, test observation and receipt root. No Setup has run.
