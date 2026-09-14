# Correct the passive filename check

Root check ca0158 failed because its filename regex omitted digits, rejecting
the selected win32 source names. The map and source bytes did not change.
Preserve that failed tool object. The separate check02 permits digits in the
same fixed source filename pattern and retains all hash, seal, commit and
fresh-output checks. This repeats a passive text check, not a candidate run.
