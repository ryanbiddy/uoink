# Preserve stored time aliases

Final diff review found that the new transcript and diarization projection omit
start_seconds/end_seconds although the renderer reads those stored fields.
Add one new regression covering all three segment containers, retain its
original-source failure, and include those aliases in the two missing allowlists.
Do not generate times or change existing assertions. Rerun the 58-case union in
the worker, apply the small raw delta with three-way apply, and rerun in checkout.
The 57-pass observations remain accurate for their earlier source.
