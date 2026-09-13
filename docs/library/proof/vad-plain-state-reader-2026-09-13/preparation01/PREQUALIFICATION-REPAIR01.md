Static review before execution found two type-boundary improvements. Require
purpose to be an exact built-in string before comparing it with synthetic.
Check the small positive deadline range before math.isfinite, so an enormous
integer is refused normally without attempting conversion to a C double.

The initial reader source is preserved in drafts. No reader, test or runtime
had executed, and no result is relabeled. The new harness will cover both
profile type refusal and huge integer deadline refusal.
