# Final originating-helper identity review

After B7 finishes, freeze its final source and run its named union before
any correction. Review whether originating-helper authority is an explicit
thread/session binding or merely equality of integer thread identifiers.
Python's [threading reference](https://docs.python.org/3/library/threading.html#threading.get_ident)
permits thread identifiers to be recycled after a thread exits. A
foreign thread must not adopt an old live writer through such a collision.

Use an isolated diagnostic with an actual originating thread and writer. Let
the originating thread exit. Model a recycled integer identifier only at
the mirror module's thread-identity query; leave actual threading operations
and the writer process real. Retain the original and final intent bytes,
real originating/current thread objects and IDs, simulated returned ID,
writer PID, and cleanup result. Label the allocator reuse simulated; do not
claim Windows was observed to recycle this identifier. The operation must
refuse without changing the intent. Keep the ordinary original-helper and
foreign-thread controls from B7 unchanged.

If this final source still grants authority by integer identity alone, make
the smallest integrator review correction after preserving the original
worker patch and result: bind the actual originating Thread object or an
equivalent explicit context, with no fallback to a different thread that
shares its integer ID. Preserve dead-session refusal and the shared gate.
This is a bounded review correction within the authorized implementation
work, not a new Ryan decision. Document the repair before rerunning. Verify
the full unchanged named union plus the new diagnostic in the worktree and
checkout, retaining separate original-worker and corrected-source hashes.

Also finish the two explicit launch-state obligations in B7's brief. A
prepared session that is cancelled and never launched must eventually release
the gate; its cancelled state must make a later launch refuse. During the
Popen-result/job-assignment handoff, cancellation must not close the job
handle while the launcher is still using it. Use controlled scheduling before
the actual job-assignment call, recording cancellation return, actual child
identity and handle-close ordering. If the original handle was closed, do not
call the kernel with that stale handle; record the ownership failure and
clean up through the original session. Do not claim an actual kernel call on
a recycled handle was observed. Any correction must keep the state lock
short and avoid holding it through Popen or pipe reads.
