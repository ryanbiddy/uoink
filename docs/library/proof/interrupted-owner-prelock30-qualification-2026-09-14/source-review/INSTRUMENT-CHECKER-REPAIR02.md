# Passive review checker correction

The first passive checker returned exit 1 in actual 0341f5 at its module-count check. Its regex, `"([a-z_]+)"`, excluded digits and omitted `win32_worker_connection` and `win32_private_pipe`. The later passive diagnostic ce6750 returned exit 0 and showed 32 matches with that regex, 34 with `"([a-z_][a-z0-9_]*)"`, and the new test module last.

The corrected checker uses the latter identifier grammar. This changes only the review instrument. The subject qualifier, launcher, tests, controls and pins remain unchanged. The failed actual is retained as INSTRUMENT-CHECK-ACTUAL.json. No candidate was executed by either check; neither supplies a test result.
