# Source review repair, 2026-09-13

The first draft was not executed. Preserve it in `before-source-review01/generated_operation_flow.py`.

Python dictionary equality permits `True == 1` and `False == 0`. Authenticated JSON decoding already bounds values, but several exact generated responses and the worker's options comparison used dictionary equality alone. Add a small recursive exact-type comparison for fixed passive payloads and use it for these comparisons. This keeps the fixed wire contract from accepting a boolean where a count is required. It adds no wire operation or native permission.

The first worker draft waited for `begin` immediately after adoption. A session that closed without calling `transcribe` would send `cancel` there and fail. Accept only an empty session-cancel payload in that position, release the exact adopted handles while no reads or native model work have begun, acknowledge closure, and retain the usual parent process/job observation. This source path is outside the two proposed positive measurements and must not be reported as measured.

No case or prior source is changed. The six ASR connection assertions and all previous native receipts remain separate and untouched.
