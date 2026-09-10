# Preserve original proof bytes

The first committed-byte audit at 393010f fails for four new probe proof files:
both results.json records and both tests.log files. The working files match the
recorded hashes; Git normalized their line endings because the new proof path
lacked the archive's no-conversion attribute. Preserve the original working
bytes, set -text for the exact path and re-add them. The failed first audit is
retained. This repairs evidence transport, not test results or acceptance rules.
