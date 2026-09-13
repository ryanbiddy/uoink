The first data-only prepare_derivative.py invocation exited 1 before creating
the repaired harness. It assumed CRLF in the original harness import line;
the exact frozen source has zero CRLF pairs and 379 LF bytes. The resulting
assertion failure was at before.count(old) == 1. No reader/harness case ran.

Preserve the first preparer under before/prepare_derivative-before-newline-repair.py.
Correct only the preparer's insertion anchor to the observed LF bytes, keeping
all source bytes otherwise intact. The first invocation had already copied the
twelve unchanged source/context inputs. A continuation must verify those exact
copies instead of overwriting them, then create the missing outputs exclusively.
No sealed input or test assertion changes. This is a preparation-script error
and cannot be counted as a reader result.
