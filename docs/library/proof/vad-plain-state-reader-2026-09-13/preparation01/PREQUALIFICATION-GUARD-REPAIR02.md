Before any execution, retain the established Windows lexical-prefix handling
in the new child guard. Remove the \\?\ or \??\ prefix from metadata-path strings
before the forbidden-directory comparison. This performs no path resolution
or metadata call on that directory. The first harness draft is preserved.
No test assertion or reader source changed, and no run occurred.
