The first read-only supplemental collector stopped at `KeyError: 'code'`.
It incorrectly assumed a top-level error code; the recorded production
envelope carries `error.code`. The collector also normalized stored corpus
CRLF when computing its first diagnostic length. Read the original bytes,
decode UTF-8 without newline conversion, and compare the entire returned
text plus original corpus hash and byte count. Reinspect the existing captures;
do not rerun the client or alter the expected packets or production code.
The initial inspection stopped before any acceptance result or archive was made.
