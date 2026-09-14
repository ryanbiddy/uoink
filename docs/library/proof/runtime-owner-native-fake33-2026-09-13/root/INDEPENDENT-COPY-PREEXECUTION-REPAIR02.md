# Independent copy preparation repair, 2026-09-13

The frozen e948c0c6 copier contains the literal @@INVENTORY_SHA@@ placeholder. Root read d4b575 found it before any invocation. Its first pinned plan read would refuse the actual inventory. No copier or candidate was run; the destination remained absent.

Keep the original 18-payload preparation and bc34510d seal unchanged. The separate root derivative copy-runtime-owner-native-confirmation02.ps1 changes exactly two lines: replace the placeholder with the reviewed inventory hash e29554fed94a2e3ec79ba0010e3e57a2a5cfbc27edfd0ee107c59e5ee68348bd, and bind PSCommandPath to the derivative's exact location. All copy modes, source checks, exclusive writes, dormant controls and postchecks remain unchanged.

Root previously read the full original copier in 3ed640. Check 7af6aa confirms the launcher changes only 37 fixed-root occurrences and the source map relocates exactly 36 paths. The 33 case bodies, qualifier and guards remain unchanged. The 42-file/569,125-byte plan is retained. This repair admits one documentary copy only; it grants no test, native, model, artifact access or real runtime authority. Preserve any partial copy on failure and do not retry automatically.
