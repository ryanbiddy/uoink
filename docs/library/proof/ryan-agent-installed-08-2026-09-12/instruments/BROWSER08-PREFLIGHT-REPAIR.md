# Browser startup and output-capture repair, 2026-09-12

The first package-08 browser command registered a network rule before navigation.
It timed out after 45 seconds. The Python wrapper remained blocked in captured
pipe cleanup until the dedicated uoink-install08 daemon was closed. No dashboard
open command or image occurred in this attempt. Its session PID file identified
12268; its control port was 49765. The same-session close returned zero, and both
the daemon and wrapper PID 33680 were subsequently absent. No broad process kill,
ordinary browser close or forbidden-port probe occurred.

Use the documented open-first workflow in fresh session uoink-install08b. The
only permitted navigation is http://127.0.0.1:18081/dashboard; allowed domains
remain 127.0.0.1. The inspected dashboard uses relative initial API requests.
Its literal 5179 is a fallback display label, not an initial fetch destination.
Register the forbidden-port abort rule after that explicit navigation. This
startup-order change is a repair hypothesis; the original rule timeout remains
failed and its internal browser cause is not proved.

The new wrapper captures stdout/stderr to files and records the CLI PID, timeout
and return code. It no longer waits for an inherited pipe to reach EOF after a
deadline. A timeout requires explicit same-session cleanup before any further
attempt. Preserve the original wrapper, this diff and both action records.

The C22 product scenarios are already completed. Its current browser hold is
still running; the new browser attempt provides the first actual visual evidence,
not a repetition or relabeling of a product measurement. Existing assertions,
fixtures and expected state stay unchanged. No source, model or external media
fetch, paid API, live-index access or port-5179 contact is permitted.
