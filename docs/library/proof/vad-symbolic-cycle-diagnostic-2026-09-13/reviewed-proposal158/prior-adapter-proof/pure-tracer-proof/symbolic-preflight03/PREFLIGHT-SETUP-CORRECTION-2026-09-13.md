# Synthetic setup correction before execution

The reviewer found that `missing_initial_protocol` supplied `b'}.'`, a
two-byte payload. The tracer correctly rejects that input at its minimum
three-byte guard before reaching the protocol check. No qualification has
run against this draft. Its exact bytes and hash are preserved in
`preflight-setup-draft01`.

Change that new synthetic input to `b'}N.'`, which is at least three bytes
and begins with EMPTY_DICT instead of PROTO. Keep its expected refusal
unchanged. Add a separate case for the original two-byte input and its
minimum-input refusal. This corrects new synthetic setup only; it changes
no tracer code, product code, accepted test or checkpoint access policy.
