# Candidate bundled-runtime guard repair

Build source: `e47e4f2e8e1b6a83ecb1171436092b9077186430`.
The local Inno build succeeded. This brief authorizes one corrected synthetic
stdio observation against its unchanged staged runtime, before installation.

## Failed observation 01

The original probe successfully imported the packaged library modules, opened
its synthetic one-item database at schema 30 and reported Python 3.11.9 with
MCP 1.27.1. Server initialization produced no response. The caller timed out;
the server exited 1 and both output drains finished.

The complete stderr identifies the harness fault: its blanket socket guard
refused Windows asyncio's internal `socket.socketpair()` self-pipe while
constructing the event loop. Preserve this failed attempt, its original probe,
generated scripts, request frame and complete stderr. It is not a runtime pass.

## Repair and next observation

Use a new fixture directory and a separately retained probe. Permit only the
standard library's internal socket-pair bind/connect, verified against the
original function's code object, local socket objects and loopback peer address.
Port 5179 remains forbidden, including this exception. Every other bind,
connect, datagram send and DNS request remains blocked. Keep the live-index
guard, isolated profile and nested-process refusal unchanged.

Run the same inventory, native/fallback card comparison, native consult prompt
and small activity request against the original staged entry point with the
embedded interpreter. Preserve complete frames and process cleanup. Do not
modify product source, dependencies or acceptance tests. A successful result
would establish only this synthetic staged-runtime scope; installed C22 and
Phase 4 client receipts remain Ryan's.

## Result and archive inspection

Observation 02 completed in the fresh fixture with the same packaged Python
3.11.9 and MCP 1.27.1: 32 tools, five templates, four prompts, equal complete
native/fallback card contents, a native consult prompt and a successful small
activity request. The child exited zero and both drains completed. Observation
01 remains failed. No product source or acceptance test changed.

The archive collector initially stopped because server import creates
`token.txt` and writes `server.log` beside the staged entry point. Neither is
selected by Inno's explicit source list; the token's creation time is after
compilation. Correct the collector to record these side effects separately,
exclude only those two non-input files and verify the remaining inputs against
the frozen source and normalized timestamps. Remove the task-created staged
token after all children have exited. Do not archive token contents. This is
an archive-inspection correction, with no runtime or build rerun.
