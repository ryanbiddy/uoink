# Glama build configuration

The root Dockerfile runs the default 92-tool stdio server on Linux. It needs no Windows helper, credentials, media downloads, or startup network access. Media capture and paid generation still require their normal runtime dependencies and consent; introspection does not exercise those features.

Glama accepts build settings in a form. Use these values with this repository checked out as the working directory. These are the settings to enter, not a Dockerfile upload. Field labels may differ in Glama's UI.

| Field | Value |
|---|---|
| Base image | `python:3.11.17-slim-bookworm` |
| Build steps | None. The server runs directly from Python sources. |
| Install steps | `python -m pip install --no-cache-dir -r requirements-mcp.txt` |
| Start command | `python -B scripts/run_mcp_container.py` |
| Working directory, if requested | Repository root, equivalent to `/app` in the Docker image |
| Secrets | None |

Paste these environment variables if the form provides an environment field. The launcher also enforces the disposable state paths, offline model settings, empty telemetry endpoint, and default toolset before importing Uoink.

```dotenv
PYTHONDONTWRITEBYTECODE=1
PYTHONUNBUFFERED=1
PYTHONUTF8=1
PIP_DISABLE_PIP_VERSION_CHECK=1
HOME=/tmp/uoink/home
XDG_DATA_HOME=/tmp/uoink/xdg
LOCALAPPDATA=/tmp/uoink/appdata
UOINK_ISOLATED_PROFILE=/tmp/uoink/profile
UOINK_ISOLATED_APP_DIR=/tmp/uoink/app
UOINK_ISOLATED_PORT=5180
UOINK_OUTPUT_DIR=/tmp/uoink/profile/output
UOINK_USAGE_ENDPOINT=
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
```

Leave `UOINK_MCP_TOOLSET` unset. Port 5180 is an isolated helper address, not a listening service started by this image. The entrypoint creates its state under `/tmp/uoink` and launches only the stdio process. The Docker image uses UID/GID `65532:65532` and copies only server source and migration files.

After the repository revision tracked by Glama contains these changes, reopen its Build page and re-run the server build to capture a fresh `tools/list` and trigger quality grading.

## Local and CI verification

```sh
docker build --tag uoink-mcp:ci .
docker run --rm --network none --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=64m \
  --entrypoint python uoink-mcp:ci \
  -B /app/scripts/smoke_mcp_container.py
```

The Ubuntu `mcp-linux-container` CI job runs these commands. The smoke test completes MCP initialization and checks the real `tools/list` against the registry, including its count, order, descriptions, and input schemas. It does not invoke capture tools. All network access ends with the image build, and the test permits writes only in `/tmp`.

## Metadata snapshot updates

Input names, types, required fields, enums, and constraints remain frozen. Tool metadata is shared by stdio, HTTP, and the CLI in `uoink_mcp_tools.py`. Input descriptions are added to a copy for clients; the raw registry schemas and phase contract snapshots remain unchanged.

With repository dependencies installed and the parent environment isolated as described in `tests/update_mcp_wire_goldens.py`, update documentation through:

```sh
python -B tests/update_mcp_wire_goldens.py --metadata-only
```

This reads the real stdio server, checks that input contracts and tool order are unchanged, then updates only descriptions, titles, annotations, output schemas, and input descriptions in the wire baseline. It preserves protocol fixtures. Review the diff and run the MCP tests, including `tests/test_mcp_metadata.py`.

The refresh also synchronizes tool descriptions in `.mcpb/manifest.json`. Stable return shapes are documented in `OUTPUT_SCHEMAS` and advertised by HTTP, which already returns `structuredContent`. Stdio keeps its existing JSON-text response contract and omits `outputSchema`: the [MCP specification](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/server/tools.mdx) requires structured results when that field is advertised. Its descriptions document return values instead. Adding structured stdio results is a separate response-contract change.
