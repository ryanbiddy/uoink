2026-09-13. The single admitted wrapper-preflight01 run passed all 12 repaired-wrapper cases, with zero failed cases, in 5.7517623 seconds on PowerShell 7.6.5. Qualification, native qualifier, launcher outer and actual tool exits were all 0. Qualifier stderr was empty. All 13 copied source/protocol/admission inputs remained unchanged.

The four original-wrapper controls matched their separate predictions and are excluded from the 12 passes. Under inherited native-command errors true, original native exits 1, 2 and 3 raised NativeCommandExitException before actual-exit.json was written. Its zero-exit control completed. The original wrapper remains unqualified.

The repaired wrapper preserved raw-exit.txt and actual-exit.json for native exits 0, 1, 2 and 3 under both preference values. Four intentional log-postcheck failures retained those native receipts and produced separate caller-process exits 91, including the case whose native child exited 0. Those expected failures remain in the raw receipts and are not labeled successful wrapper executions.

This run executed the exact reviewed wrappers only against the hash-bound inert child. Neither real D1 Python entry, an inspection helper, the checkpoint, a model package nor a network request was invoked. Both original D1 owner pins remain None. The first documentary sealer refusal remains preserved; there was no qualification retry or source correction after this run.

This result qualifies the described wrapper exit-accounting cases. It does not qualify an actual D1 invocation, filesystem power-loss behavior, model conversion, runtime safety or release readiness. The preparation manifest remains unchanged at f0e7b975f089ab176b9db97a234e6cc2d42ae717594d454f35223aebfc2d0e93.
