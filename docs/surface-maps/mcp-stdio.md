# Surface map: MCP stdio entry point

`uoink_mcp.py`: the process MCP clients (Claude Desktop, Cursor, Cline)
launch and speak JSON-RPC with over stdin/stdout. Fixed in C-01 (CRIT-1);
before that fix this path had NEVER worked on an installed copy.

## The bug that shipped for months

The installer bundles the embeddable Windows Python. Its `._pth` file
(`python311._pth`: `python311.zip`, `.`, `import site`) locks `sys.path`
to the interpreter's own directory, and the embeddable distribution never
adds the script's folder. So `python.exe uoink_mcp.py` imported the `mcp`
SDK fine (it lives in the bundled site-packages) and then died on
`import server` with `ModuleNotFoundError`. Claude Desktop logged 22
crashes, 0 successful connections. Dev and CI interpreters DO add the
script dir, which is why nothing ever caught it.

## The fix

Top of `uoink_mcp.py`, before any sibling import:

```python
_APP_DIR = str(Path(__file__).resolve().parent)
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)
```

Nothing in installer/staging changed; the fix travels with the file, so
existing installs heal on their next app update, and every first-party
config generator's emitted command (`python.exe uoink_mcp.py`) starts
working as-is.

## Boot sequence (unchanged apart from the pin)

1. Pin the app dir onto `sys.path`.
2. Import the `mcp` SDK (exit 1 with an actionable message if absent).
3. Swap `sys.stdout` to stderr while importing `server` (server.py wires a
   stdout log handler at import time; stdout belongs to the protocol).
4. `uoink_mcp_tools.bind_backend(server)`, build the FastMCP app, and
   register exactly the 14 canonical `@mcp.tool`s. The six Yoink-era aliases
   completed their compatibility window in v2.5 and are absent in v3.

## How it can never silently regress

- **`tests/test_c01_mcp_stdio.py`** re-creates the embeddable condition on
  any interpreter with `python -P` (PYTHONSAFEPATH withholds the script
  dir, same effect as the `._pth`), from a non-repo cwd, and drives the
  real client handshake: initialize -> notifications/initialized ->
  tools/list (exactly 14 canonical tools) -> tools/call
  `list_recent_uoinks` against an
  isolated data root (`LOCALAPPDATA`/`XDG_DATA_HOME`/`UOINK_OUTPUT_DIR`
  pointed at a temp dir; the test never touches a real index). CI's
  stdlib-tests job now installs the `mcp` SDK so this runs, and the test
  skips LOUDLY (printed reason) if the SDK is missing locally.
- **`--doctor`** gained `mcp_stdio`: `_mcp_stdio_selfcheck()` in server.py
  spawns `sys.executable -P uoink_mcp.py` and walks initialize ->
  tools/list, reporting `{ok, tools}` or `{ok: false, error}` with the
  subprocess's stderr tail. On an installed copy that's the bundled
  embeddable interpreter, i.e. the real-world path. Support triage sees a
  dead agentic path immediately instead of a green report.

## Driving it by hand

```
python -P uoink_mcp.py
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"me","version":"0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
```

One request in flight at a time; the server answers each before reading
the next reliably, and batch-piping all messages then closing stdin can
drop late responses (observed with tools/call in a 4-message batch).

## Verified on the real thing

Gate run 2026-07-04/05 against the installed embeddable interpreter
(`%LOCALAPPDATA%\Uoink\python\python.exe`) driving this repo's
`uoink_mcp.py`: initialize answered (`serverInfo.name: "uoink"`),
tools/list returned 20 at the time because six deprecated aliases were still
registered; `tools/call list_recent_uoinks` returned
`{"ok": true, "yoinks": []}` against an isolated temp index. The v3
regression gate now requires exactly 14 canonical names and rejects the six
removed names. The same sequence on the original C-01 file exits 1 with the
ModuleNotFoundError.
