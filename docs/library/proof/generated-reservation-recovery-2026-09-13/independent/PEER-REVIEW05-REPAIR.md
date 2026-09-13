# Preserve the active record's reservation

Independent review found that a new physical snapshot under the same semantic
key could overwrite the active record's token before the base lease rejected
that key. Later quarantine then targeted the wrong physical journal. The
unexecuted source and tests are retained under `before-peer-review05/`.

A manager-owned entry slot will bind the exact entering lease before journal
work. The manager checks both this slot and any active semantic record, then
rechecks before installing the returned token. The slot remains held until base
entry finishes. Journal I/O stays outside the manager lock. A post-begin loser
quarantines its own retained token directly and cannot update the old record or
route quarantine through its semantic key.

Two generated controls cover two physical journals under one active semantic key
and a deterministic second entrant during the first reservation callback. The
physical gate still collides by volume/file identity alone; this connection slot
adds no alternate physical gate. A third control verifies that reserve, bind,
clear and quarantine sync hooks run outside the manager state lock. Planned case
count becomes 42; no execution.
