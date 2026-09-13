# Reproduce remaining identity boundaries before any real process test

The worker patch passes eleven synthetic cases. Independent source review finds
that it still uses a two-second tolerance to authorize PID mutation and admit
children older than their parent. It also reads child identity after a stale
Toolhelp snapshot without revalidating the relationship; parent identity is
checked only before enumeration. A missing recorded parent timestamp can be
filled from a later raw PID lookup. These boundaries require direct synthetic
observations before acceptance. The original tree08 cause remains unproved.

Run new Astra boundary probes only against the unchanged worker patch. Every
OS, process and kernel observation is an inert fake; effect recorders must show
whether mutation was requested. Cover small timestamp mismatch, an older orphan,
an unrecorded parent identity, parent and child replacement during enumeration,
and Popen-confirmed death with a same-PID writer whose timestamp query failed.
Do not run real mirror suites or modify existing/worker assertions. Preserve
the exact new test and all failed outcomes. Any reproduced gap requires a
documented product repair before a fresh observation.
