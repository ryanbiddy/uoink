# Windows namespace and protocol contracts: accepted within tested scope

2026-09-13. Astra accepts the exact protocol, namespace and pipe state handling
tested by 54 generated-memory cases. The author and independent root each passed
54, with zero failures and skips. Their ordered case objects match. This is one
54-case set repeated independently, not 108 distinct cases.

Author nsp01 took 0.017906299995956942 seconds; actual tool 0a8066 returned zero
in 0.6375469 seconds. Independent root nsp01 took 0.01751979999244213 seconds;
actual tool 91ffc7 returned zero in 0.5615508 seconds. Both raw tool objects,
immediate native exits, admissions, source copies, before/after bindings and
raw results are retained. Each run has twelve metadata traps and twenty-five
registry traps, valid guards, no denials or heavy imports, empty stderr and nine
unchanged inputs. Root comparison c8b2e4 was observed; no separate raw object was
saved for that comparison and none is reconstructed.

Review repairs before the first run bounded passive protocol values, checked
the exact worker registry, serialized channel operations, clarified the logical
payload budget, retained partial pipe resources and added a bounded stop attempt
after quarantine. Drafts and reasons remain in the original 37-payload seal,
412ff1c34376f0ce156c055e27afc66e9d19ed3ed7358f939e7f8df1b526f02f.

Root read the documentary builder d49ba298 and verifier 3133df16 in full before
invocation. Build b0529b and verification 289171 returned zero; they executed no
tests. The proof contains 65 payloads, 509,620 bytes and 87 logical members mapped
to 57 distinct objects. Its seal is
34b4c1d9252c02f65d2756adf35c6b3484738939d717a973bb5230391868f1b0.
The outer seal filename becomes SHA256.json in the repository; its bytes and
all payload bytes are unchanged. The original nested seal remains intact.

These cases use fake APIs. ControllerHandshake's lifecycle and permit methods
are source-reviewed only in this set. Actual Win32 calls, process inheritance,
child-held file protection, native CTranslate2 behavior, child model read-set
reconstruction and model memory behavior remain untested here. The separate
generated-data Windows flow must pass before it earns those narrower claims.
No model, installation or market acceptance follows from this verdict.
