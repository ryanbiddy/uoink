# macOS process identity repairs and lifecycle handoff

Base: `e104473`, existing `mac/pass2-state` worktree. No commits or git ref changes.

This change repairs the four failures reported from hosted run `39221995125`
and implements plan pass 4. Native macOS acceptance remains pending; Windows
tests cannot qualify libproc, POSIX signals, or APFS locking.

| Reported failure | Cause and change |
| --- | --- |
| `test_unavailable_creation_lookup_is_not_owned` | The Darwin branch bypassed the creation-lookup boundary exercised by the test. A native alive result now also requires the consumer's creation lookup to succeed and match exactly. Missing birth data returns unknown. |
| `test_vault_io_worker_startup_and_terminate_are_real` | Mirror liveness compared the worker's native image with the observer's `sys.executable`. Framework Python can exec a different image from that launcher. The observational probe now checks PID/birth without inventing an expected image. Mutation authority comes from the retained supervisor. |
| `test_inflight_isolated_intent_put_cannot_finish_after_writer_death` | The hosted trace fails in the stall proof, before termination: SIGSTOP succeeded, but the same image comparison made `writer_alive` false. Stopped Darwin status 4 remains alive. Tests retain the real SIGSTOP/pending-RPC/SIGKILL sequence. |
| `test_owned_stop_waits_for_exit_before_unlinking_identity` | A native absence observation can precede waitable exit, and the fixture also sampled identity during startup. Darwin stop now registers kqueue NOTE_EXIT before SIGTERM and requires that event before reporting success. The fixture waits for readiness before sampling and reaps its retained child with a bounded wait. No longer sleep was added. |

Subscription incarnation probes had the same inferred-image problem. They now
check exact birth identity without assuming the observer's launcher image.
Persisted child records still check their explicitly observed executable.

`uoink_processes.PosixChild` runs a supervisor in a private session. The
supervisor forks an anchor that owns the workload group; the actual command and
its ordinary descendants inherit that group. The supervisor retains the anchor
until cleanup ends, preventing reuse of the numeric group ID during signaling.

The caller holds the sole parent-lifetime pipe writer. Cancellation closes it;
parent death closes it in the kernel. Either event, command exit, or command
crash starts group termination. The supervisor repeats SIGKILL and checks for
remaining executable members using libproc on Darwin and procfs on Linux.
Zombies count as exited. Callers have bounded waits, and uncertain death retains
the supervisor, anchor, and borrowed admission locks. It does not authorize a
replacement writer.

The anchor also watches a supervisor-lifetime pipe and kills its own group if
the supervisor dies. A caller missing the supervisor's completion record reports
unconfirmed cleanup. Parent pipe writers are closed in forked children so an
unrelated fork cannot keep a dead parent's jobs alive.

Server capture records follow the supervisor PID through descendant cleanup.
The public child PID still identifies the command, including the real vault
writer. Mirror admission retains the same flock open-file description in the
supervisor, so parent death does not release admission before the group drains.
Receipt sessions report group cleanup explicitly without claiming a Windows
Job Object query succeeded.

This contract covers commands that retain the inherited process group. It is
not a sandbox for programs that deliberately daemonize or call `setsid()`.
Native tests use synthetic descendant trees and the real vault worker. They do
not qualify the eventual packaged yt-dlp or FFmpeg binaries.

The POSIX paths are used by server extraction jobs, vault I/O workers, receipt
sessions, podcast downloads, and default playlist polling. Windows Popen flags,
Job Object operations, and msvcrt lock implementations remain unchanged. The
new helper is included in both build payload lists and the installer source list.

Changed files:

- Runtime: `uoink_processes.py`, `uoink_install_isolation.py`, `library_mirror.py`,
  `server.py`, `source_subscriptions.py`, `podcasts.py`, `mobile_playlists.py`,
  and `scripts/install_receipt/p4_session.py`.
- Payload lists: `build-mac.sh`, `build.ps1`, and `installer/uoink.iss`.
- Tests: `test_mac_process_identity.py`, `test_mac_process_lifecycle.py`,
  `test_mac_posix_locks.py`, `test_install_isolation_repair.py`,
  `test_child_and_memory.py`, `test_sec_ssrf.py`, and
  `security/test_security_findings.py`, all under `tests/`.
- Handoff: this file. Frozen receipt/proof fixtures were not changed.

New tests cover cancellation, timeout, normal command exit with leftover
descendants, command/owner/supervisor death, suspended descendants, foreign
process survival, repeated termination, missing cleanup proof, and retained
admission locks. Four lock families exercise real cross-process contention,
SIGKILL of the holder, acquisition by the waiting contender, and restart with
the same lock inode: capture, library store, mirror ledger, and mirror admission.

Windows verification used ig-native Python 3.14.6. The running interpreter's
priority was checked as BelowNormal. Results:

| Run | Passed | Skipped | Expected failures |
| --- | ---: | ---: | ---: |
| Main regression set | 3,292 + 6 subtests | 112 | 1 |
| Supplemental tests, including the resumed portion | 2,118 + 6 subtests | 19 | 0 |
| Final process/mirror/macOS-focused checks | 312 + 6 subtests | 24 | 0 |

These runs overlap. Deduplicating their JUnit cases gives **4,725 passed
(including subtests), 118 skipped, and one existing expected failure**, with no
unexpected failures. The expected failure is the archived AT6 receipt gap in
`test_as7_c21_at6_receipt_records_process_exit_status`.

The supplemental run's progress reporter initially collided with a test's
`Path.open` spy. The reporter was corrected to use its captured open function;
the 242 recorded passing test IDs were deselected on resumption, and all
remaining tests ran. This changed only the temporary harness.

The local equivalents of all four `ci.yml` static jobs passed: extension
JavaScript syntax, cached ESLint 8.57.1 checks, JSON/version/log guards, backend
compilation, MCP inventory, and the readiness bash syntax fallback. The inventory
is 91 full / 35 core tools. `build-mac.sh` syntax and `git diff --check` also pass.

Evidence is under
`C:/Users/hello/AppData/Local/Temp/uoink-mac-pass3-80c2732a/`:
`verification-summary.json`, `regression.xml`, `extra/results.xml`,
`extra/resumed.xml`, and `final.xml`.

The harness established an isolated profile
before product imports, disposable home/data/output directories, PYTHONPATH,
IG_FORBIDDEN_LIVE, and guards against the real token/settings paths, live Uoink
data, port 5179, and external network. Scratch and test evidence are under TEMP.

For hosted acceptance, run the complete portable suite on macos-15 arm64 under
Python 3.11 and 3.13, including `test_mac_process_identity.py`,
`test_mac_process_lifecycle.py`, `test_mac_posix_locks.py`, and the original four
failing cases. Confirm actual libproc group enumeration, stopped-process
liveness, exit/reaping behavior, parent-death cleanup, and APFS flock recovery.
Dependency graph/import smoke passed in run `39221995125`; they were not rerun
locally. Mirror publication exclusion remains plan pass 5.
