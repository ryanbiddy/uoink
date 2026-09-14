# Source-only diagnostic bindings

The initial proposal03 copies retained proposal02 paths while the reporting delta
was reviewed. Before final binding, those drafts were copied unchanged to
before-final-bindings. The bootstrap and launcher now name only the fresh
writer-exclusion03 output. The launcher change is limited to those fixed paths
and its own filename; all receipt checks and native-exit handling remain intact.

SOURCE-INPUTS.json binds the 18 local source files. Its nine support-file entries
are copied historical bindings, not a new observation of installed files. The
admission template remains false and binds the new map and launcher. No candidate
source, test, native operation or launcher was executed during preparation.

The port catches only the existing comparison's PersistenceUnconfirmed, attaches
already observed immutable values and re-raises the same exception. Its output
helper is passive. The bootstrap adds a null-or-bounded directory_refusal field;
the original failure, quarantine and pending-I/O finalizer remain in place.
No mismatch field or root cause is claimed until an admitted run supplies it.
