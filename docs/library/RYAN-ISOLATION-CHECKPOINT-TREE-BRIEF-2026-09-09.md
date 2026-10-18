# Integrated isolation checkpoint — 2026-09-09

Product source changed after complete tree 263b7e4: existing reads preserve
storage at e86bc16, and the isolated installer/helper/stdio source integrates
at 022ff43. Focused unions are reviewed. Run the complete tree at the next
committed checkpoint while the two receipt instruments finish independently.
This is a source checkpoint, not the final kit-inclusive observation or release.

Use the private native Python 3.14.6 runner, audit guards and fresh disposable
environment already sealed in proof/ryan-verification-runtime-2026-09-09.
Run tests with only the historically separate tests/library_work_astra/test_phase3_s21.py
excluded. No existing acceptance test edits, extra deselection, invented skip,
paid API, live index, 5179, client/model run, Inno execution or label application.

Compare case membership and exact failed IDs against the complete 263b7e4 XML.
The eight mirror-hook failures and historical AT6 exit gap remain expected
failures, never exclusions or passes. The pending fixture proposal is unapplied.
New failures require a documented repair and bounded reproduction; do not alter
fixtures further. Preserve all logs/XML/counts with source commit and hashes.
Final integrated kit changes still require their named verification and a final
committed full tree before the owed rebuild and complete operator runbook.
