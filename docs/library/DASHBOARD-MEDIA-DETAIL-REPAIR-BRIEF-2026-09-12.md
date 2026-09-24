# Repair saved media details without widening the file endpoint

Ryan requested complete checks, native GUI checks and fixes. While reviewing the
note display repair, Astra confirmed a second production defect: dashboard
loadJsonFile requests a .json sidecar through /file, which intentionally serves
images only and returns HTTP 415 for JSON. Video/podcast details therefore cannot
load their saved metadata. The catch message says to wait although retrying the
same request cannot work. Notes now use their saved text and must keep working.

Write docs/library/DASHBOARD-MEDIA-DETAIL-WORKER-2026-09-12.md early. Read this
brief and NATIVE-NOTE-DISPLAY-INTEGRATOR-REPAIR-2026-09-12.md. Scope is only the
saved detail read path in server.py and assets/dashboard/index.html, plus new
focused regressions. No existing test, fixture, assertion or mark may change.

Prefer an existing authenticated item-ID route if one can provide the required
saved fields. Otherwise add a narrow authenticated GET /yoinks/<id>/details
route. Look up the item in the index and use its registered sidecar path; never
accept an arbitrary client path. Resolve and contain the path under DESKTOP_ROOT
before opening it, reject escape/symlink cases, and bound the JSON read. Return
only saved fields needed by this dashboard (not arbitrary secrets from a file).
Missing, malformed, oversized and non-object JSON must return a clear error;
do not fake an empty successful sidecar. Keep /file image-only and every existing
token/origin boundary intact. No new fetch, extraction, writing or inference.

Wire openYoinkDetail to the safe route and show an honest unavailable/error state
after refusal, not perpetual checking or ready. Retain actual saved timestamps,
cues and screenshot references without inventing any. No speaker attribution
claims or runs: handling saved fields is not permission to generate them. Notes
must keep the new source-aware labels and measured text readiness. Avoid stale
async responses overwriting a different selected item if touching that path.

Add new behavioral regressions for successful saved video metadata, authentication,
unknown ID, missing/corrupt/oversized JSON, out-of-root file refusal without reads,
and Node-executed dashboard loading/error/selection behavior. Use real temporary
index rows and files plus the existing test request/renderer adapters; no actual
helper or browser. Demonstrate the new cases on the original source first, then
repair and use fresh labels. Preserve all attempts and diagnose before rerunning.

Named suites: tests/test_dashboard_v324_ui.py, tests/test_screenshots_reyoink.py,
tests/test_screenshots_picker_v324.py, tests/test_note_readiness_truth.py,
tests/security/test_security_findings.py and the new focused regression file.
Use E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/ig-native/Scripts/python.exe
with the external _scratch/integrator_verify.py, --root your worktree, fresh
labels, and --runxfail for the unchanged SEC-06 assertion. Set IG_FORBIDDEN_LIVE
to the literal forbidden path before launching Python; scrub paid provider/API
variables without printing values. No tests are waived by --runxfail.

No live index access including stat/hash, no port 5179, no helper/GUI/build/install,
no network or new dependencies, no paid API, model loading/download/inference,
diarization, credential access, commits, pushes or subagents. Apply stays false.
Do not alter the handoff or release notes. Astra independently verifies and
integrates the raw diff with three-way apply. A fresh complete tree and installed
package qualification will follow; the currently running a25e3be tree stays its
own dated observation. This worker does not approve a release.
