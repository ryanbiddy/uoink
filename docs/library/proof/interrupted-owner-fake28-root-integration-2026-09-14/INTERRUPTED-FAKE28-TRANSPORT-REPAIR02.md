# Restore exact sealed bytes after Git application

2026-09-14. Copy ab7b19 sealed404 payloads/5,257,972 bytes. Raw worktree diff and root --3way application882803 returned0. Passive transport check1e61c5 failed at .gitattributes: application changed raw new-file line endings despite per-command core.autocrlf=false. The first check remains failed. No subject tests were rerun and no behavior result changes.

For this exact new archive only, compare every donor file against its original seal, then require every changed checkout file to differ solely by CRLF/LF normalization. Refuse any other difference. Restore those exact donor bytes without changing the seal, record each restored path/size, then rerun the same passive transport check and the Git-index verifier after staging. This repair is byte transport, not a test or fixture correction.
