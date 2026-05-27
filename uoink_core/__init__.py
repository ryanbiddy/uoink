"""uoink_core -- internal package for the Uoink helper (Sprint 21 split).

server.py is being decomposed from a ~6k-line god module into focused
submodules. This package holds the pieces; server.py re-exports what it moves
here so the HTTP contract and MCP tool signatures stay byte-for-byte stable
throughout the refactor.

Modules (added incrementally, lowest-risk first):
- storage.py   -- pure filesystem/path helpers (atomic writes, writable probe)
"""
