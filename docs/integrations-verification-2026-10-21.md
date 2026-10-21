# Integration verification, 2026-10-21

Completed in `Yoink-integrations2` on `feat/integrations-verify`, still at
`f45ee1e`. There are 48 entries: 10 added, 45 with verified official documentation,
and 3 explicitly unverified. Actual client acceptance remains not yet tested.
All source links below were checked on 2026-10-21.

Zed's gap is its conflicting Mac settings paths, not the MCP object shape.
Legacy Kilo has no verified current legacy schema. Smithery has current local
MCPB publishing docs but no established local `smithery.yaml` command schema.

| Client | Change | Verified source | Checked |
|---|---|---|---|
| claude-code | Place environment options before the server name as the current CLI docs require. | Yes: [official docs 1](https://code.claude.com/docs/en/mcp) | 2026-10-21 |
| claude-desktop | Rechecked format and platform paths; added official sources and date. | Yes: [official docs 1](https://modelcontextprotocol.io/docs/develop/connect-local-servers) | 2026-10-21 |
| cursor | Rechecked format and platform paths; added official sources and date. | Yes: [official docs 1](https://cursor.com/docs/mcp) | 2026-10-21 |
| codex | Rechecked format and platform paths; added official sources and date. | Yes: [official docs 1](https://developers.openai.com/codex/mcp) | 2026-10-21 |
| gemini | Rechecked format and platform paths; added official sources and date. | Yes: [official docs 1](https://geminicli.com/docs/tools/mcp-server/) | 2026-10-21 |
| vscode | Rechecked format and platform paths; added official sources and date. | Yes: [official docs 1](https://code.visualstudio.com/docs/agents/reference/mcp-configuration) | 2026-10-21 |
| windsurf | Follow current docs to Devin Desktop legacy Cascade paths; identify older Windsurf separately. | Yes: [official docs 1](https://docs.devin.ai/desktop/cascade/mcp) | 2026-10-21 |
| cline | Rechecked format and platform paths; added official sources and date. | Yes: [official docs 1](https://docs.cline.bot/mcp/mcp-overview) | 2026-10-21 |
| zed | Confirm flat context_servers; flag conflicting Mac path docs and use Open Settings File. | No: [official docs 1](https://zed.dev/docs/ai/mcp), [official docs 2](https://github.com/zed-industries/zed/blob/main/docs/.doc-examples/configuration.md), [official docs 3](https://zed.dev/docs/debugger) | 2026-10-21 |
| goose | Verify extensions/cmd/envs; correct the Windows config directory. | Yes: [official docs 1](https://github.com/aaif-goose/goose/blob/main/documentation/docs/guides/config-files.md) | 2026-10-21 |
| opencode | Rechecked format and platform paths; added official sources and date. | Yes: [official docs 1](https://opencode.ai/docs/mcp-servers/), [official docs 2](https://opencode.ai/docs/config/) | 2026-10-21 |
| lm-studio | Verify mcpServers and Windows/Mac .lmstudio/mcp.json locations. | Yes: [official docs 1](https://lmstudio.ai/blog/lmstudio-v0.3.17), [official docs 2](https://lmstudio.ai/docs/app/mcp) | 2026-10-21 |
| hermes | Verify mcp_servers; correct Windows source/CLI data root and document HERMES_HOME. | Yes: [official docs 1](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp), [official docs 2](https://hermes-agent.nousresearch.com/docs/getting-started/installation/) | 2026-10-21 |
| warp | Rechecked format and platform paths; added official sources and date. | Yes: [official docs 1](https://docs.warp.dev/agents/capabilities/mcp/) | 2026-10-21 |
| junie | Rechecked format and platform paths; added official sources and date. | Yes: [official docs 1](https://junie.jetbrains.com/docs/junie-cli-mcp-configuration.html) | 2026-10-21 |
| amp | Correct Windows from APPDATA to the user .config/amp directory. | Yes: [official docs 1](https://ampcode.com/docs/customize/mcp), [official docs 2](https://ampcode.com/docs/cli/settings) | 2026-10-21 |
| roo | Rechecked format and platform paths; added official sources and date. | Yes: [official docs 1](https://roocodeinc.github.io/Roo-Code/features/mcp/using-mcp-in-roo/) | 2026-10-21 |
| kilo | Rechecked format and platform paths; added official sources and date. | Yes: [official docs 1](https://kilo.ai/docs/automate/mcp/using-in-kilo-code) | 2026-10-21 |
| kilo-legacy | Replace an unverified obsolete config with migration guidance. | No: [official docs 1](https://kilo.ai/docs/automate/mcp/using-in-kilo-code) | 2026-10-21 |
| cherry-studio | Use documented separate fields rather than assuming a JSON import wrapper. | Yes: [official docs 1](https://docs.cherryai.com.cn/advanced-basic/extensions/mcp) | 2026-10-21 |
| jan | Use documented separate fields rather than assuming a JSON import wrapper. | Yes: [official docs 1](https://docs.jan.ai/desktop/mcp) | 2026-10-21 |
| librechat | Rechecked format and platform paths; added official sources and date. | Yes: [official docs 1](https://www.librechat.ai/docs/configuration/librechat_yaml/object_structure/mcp_servers) | 2026-10-21 |
| msty | Tool Configuration takes a bare command/args/env object. | Yes: [official docs 1](https://docs.msty.ai/studio/toolbox/tools) | 2026-10-21 |
| boltai | Verify ~/.boltai/mcp.json and settings editor; restrict to macOS. | Yes: [official docs 1](https://docs.boltai.com/docs/plugins/mcp-servers) | 2026-10-21 |
| continue | Add standalone YAML metadata. Dashboard refuses the obsolete JSON write and points to manual merging. | Yes: [official docs 1](https://docs.continue.dev/customize/deep-dives/mcp) | 2026-10-21 |
| raycast | Use documented Stdio form and JSON argument array, not an assumed import wrapper. | Yes: [official docs 1](https://manual.raycast.com/ai/model-context-protocol), [official docs 2](https://www.raycast.com/changelog/windows) | 2026-10-21 |
| open-webui | Verify mcpo JSON; document native Streamable HTTP and custom headers. | Yes: [official docs 1](https://github.com/open-webui/mcpo), [official docs 2](https://docs.openwebui.com/features/extensibility/mcp/) | 2026-10-21 |
| anythingllm | Verify Desktop storage roots, plugins config file and Agent Skills refresh. | Yes: [official docs 1](https://docs.anythingllm.com/mcp-compatibility/desktop), [official docs 2](https://docs.anythingllm.com/mcp-compatibility/overview), [official docs 3](https://docs.anythingllm.com/installation-desktop/storage) | 2026-10-21 |
| ollama | Runtime has no MCP client config; direct users to actual clients. | Yes: [official docs 1](https://docs.ollama.com/capabilities/tool-calling), [official docs 2](https://docs.openwebui.com/features/extensibility/mcp/), [official docs 3](https://docs.continue.dev/guides/ollama-guide) | 2026-10-21 |
| smithery-local | Current docs mention MCPB publication; no local YAML schema verified. | No: [official docs 1](https://smithery.ai/docs/build/publish) | 2026-10-21 |
| windows-odr | Document the positional local manifest argument. | Yes: [official docs 1](https://learn.microsoft.com/en-us/windows/ai/mcp/servers/mcp-manual) | 2026-10-21 |
| obsidian | Document Windows mirror, URI and Mac gate/read-only alternative. | Yes: [official docs 1](https://help.obsidian.md/uri) | 2026-10-21 |
| n8n | Add credential fields and HTTP Streamable MCP Client Tool route. | Yes: [official docs 1](https://docs.n8n.io/integrations/builtin/credentials/httprequest/), [official docs 2](https://docs.n8n.io/integrations/builtin/cluster-nodes/sub-nodes/n8n-nodes-langchain.toolmcp/), [official docs 3](https://github.com/n8n-io/n8n/releases/tag/n8n%401.114.0) | 2026-10-21 |
| make | Distinguish cloud runners from the separate Enterprise on-prem agent. | Yes: [official docs 1](https://help.make.com/on-premise-agent) | 2026-10-21 |
| zapier | Make the local-only limitation and n8n alternative explicit. | Yes: [official docs 1](https://help.zapier.com/hc/en-us/articles/44391646192397-Ways-to-make-API-requests-in-Zapier) | 2026-10-21 |
| autohotkey | Rechecked format and platform paths; added official sources and date. | Yes: [official docs 1](https://github.com/AutoHotkey/AutoHotkeyDocs/blob/v2/docs/lib/Run.htm) | 2026-10-21 |
| powertoys | Use the documented Run commands route. | Yes: [official docs 1](https://learn.microsoft.com/en-us/windows/powertoys/command-palette/overview) | 2026-10-21 |
| alfred | Use the shipped Mac CLI shim and refuse other platforms. | Yes: [official docs 1](https://www.alfredapp.com/help/workflows/actions/run-script/) | 2026-10-21 |
| kiro | Added global/project mcpServers JSON recipe. | Yes: [official docs 1](https://kiro.dev/docs/mcp/configuration/) | 2026-10-21 |
| copilot-cli | Added GitHub Copilot CLI mcp-config.json, local type and tools list. | Yes: [official docs 1](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers) | 2026-10-21 |
| auggie | Added Augment user settings on Mac; refuse native Windows because official setup requires WSL. | Yes: [official docs 1](https://docs.augmentcode.com/cli/integrations), [official docs 2](https://docs.augmentcode.com/cli/setup-auggie/install-auggie-cli) | 2026-10-21 |
| factory-droid | Added global/project .factory/mcp.json with stdio type. | Yes: [official docs 1](https://docs.factory.com/harness/mcp) | 2026-10-21 |
| qwen-code | Added global/project .qwen/settings.json recipe. | Yes: [official docs 1](https://qwenlm.github.io/qwen-code-docs/en/users/features/mcp/) | 2026-10-21 |
| crush | Added current crushrc Bash builtin recipe, including Windows; preserve spaced arguments. | Yes: [official docs 1](https://github.com/charmbracelet/crush/blob/main/README.md) | 2026-10-21 |
| antigravity | Added shared .gemini/config/mcp_config.json and project .agents/mcp_config.json. | Yes: [official docs 1](https://www.antigravity.google/docs/mcp) | 2026-10-21 |
| chatbox | Added desktop local stdio fields and Test-before-save step. | Yes: [official docs 1](https://api.chatboxai.app/en/guide/work-mode/configuration) | 2026-10-21 |
| dive | Added mcpServers JSON with enabled:true. | Yes: [official docs 1](https://github.com/OpenAgentPlatform/Dive/blob/main/MCP_SETUP.md) | 2026-10-21 |
| perplexity | Added Mac-only local MCP helper and Simple command setup. | Yes: [official docs 1](https://www.perplexity.ai/help-center/en/articles/11502712-local-and-remote-mcps-for-perplexity) | 2026-10-21 |

## Skipped clients

| Client | Official source checked | Reason |
|---|---|---|
| Trae | [MCP docs](https://docs.trae.ai/ide/model-context-protocol) | Repeated fetch failures prevented verification of the current format and paths. |
| Witsy | [README](https://github.com/Kochava-Studios/witsy/blob/main/README.md) | The reviewed official docs confirm MCP support but do not establish the local config/import format. |
| 5ire | [Docs](https://5ire.app/docs), [README](https://github.com/nanbingxyz/5ire) | The reviewed documentation does not establish a complete local config/import format. |
| DeepChat | [Official repository](https://github.com/ThinkInAIXYZ/deepchat) | The reviewed README and architecture docs confirm MCP support without a user-facing local config recipe; the CLI guide fetch failed. |

## Files changed

| Files | Purpose |
|---|---|
| `uoink_connect.py`, `uoink_cli.py` | Recipes, platform paths and refusals, sources, dates and stderr verification status. |
| `server.py` | Prevent the obsolete Continue dashboard write. Continue setup and detection are manual; the dashboard does not parse its YAML. |
| `docs/connect-your-agent.md`, `agent-kit/README.md` | Complete generated client tables and current setup instructions. |
| `scripts/build_agent_kit.py` | Generate and check both tables alongside skill copies and plugin version. |
| `tests/test_agents_connect.py`, `tests/test_agent_connect.py`, `tests/test_agent_cli.py`, `tests/test_mac_delivery.py`, `tests/test_integrations_recipes.py` | Temp-home isolation, current formats, platform output, quoting, unchanged stdout, and config preservation. |
| `tests/fixtures/connect_20261021/changes.json`, `tests/fixtures/connect_20261021/recipes.json` | Reasons for intentional changes and 47 replacement/addition output snapshots across Windows and Mac. Historical v3.10.0 fixtures remain untouched. |
| `docs/integrations-verification-2026-10-21.md` | This report. |

The root README has no stated client count, so it needed no edit. Scratch
verification scripts and logs are confined to `_scratch/integrations-verify/`.
No mirror implementation, commit, push or ref was changed.

## Commands and results

The final Windows run used
`E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/ig-native/Scripts/python.exe`,
`IG_FORBIDDEN_LIVE=C:UsershelloAppDataLocalUoinkindex.db`,
`PYTHONDONTWRITEBYTECODE=1`, and `PYTHONPATH` containing this worktree plus the
scratch guard. HOME, USERPROFILE, APPDATA, LOCALAPPDATA, output and the isolated
profile all pointed inside scratch. The Python guard set and checked
**BelowNormal** priority and blocked the live paths and port 5179.

| Command or check | Result |
|---|---|
| `git log --oneline -8`, required source/fixture/handoff reads | Completed before edits. |
| `python -B scripts/build_agent_kit.py` | Regenerated both client tables; skill copies and plugin version already matched. |
| `python -B -m pytest tests/test_agents_connect.py tests/test_agent_cli.py tests/test_agent_cli_gates.py tests/test_agent_connect.py tests/test_installer_files_complete.py tests/test_integrations_recipes.py tests/test_mac_delivery.py -q -rs --basetemp _scratch/integrations-verify/pytest-final -p no:cacheprovider` | **276 passed, 5 skipped**, 28.69 seconds. Includes every test file mentioning `uoink_connect` and every `test_agent_cli*.py`. |
| `python -B tests/test_agents_connect.py` | All standalone checks passed under temporary homes. |
| `python -B scripts/build_agent_kit.py --check` | Passed, including docs/table drift checks. |
| `python -B scripts/check_mcp_inventory.py` | Passed: full 91, core 35; registry, docs, bundle and receipt agree. |
| `node --check` on all `extension/**/*.js` | Passed, 13 files. |
| Cached ESLint **8.57.1**, with the exact `ci.yml` environments, globals and rules | Passed; no package download. |
| JSON parsing of manifest, prompts and topics; single manifest version; VERSION parity; noisy-log guard | Passed. |
| `py_compile.compile` on all eight backend files named by CI | Passed; generated bytecode confined to scratch. |
| `bash -n scripts/verify-launch-readiness.sh` | Passed. Used CI's documented fallback because shellcheck is absent. |
| `git -c core.longpaths=true diff --check`; branch and HEAD checks | Passed; branch and HEAD unchanged. The one-command long-path option avoids false status entries when the temporary home hides the normal Git settings. |

The five skips are the existing symbolic-link tests: Windows returned
`WinError 1314` because this account lacks symlink creation privilege. The
Windows junction case passed. The run reported 36 existing `datetime.utcnow()`
deprecation warnings. An earlier run passed 275 tests before the final list
test was added; a priority check then caught a wrapper issue. It was fixed and
the complete focused run above was repeated at BelowNormal.

All four CI static jobs passed through the scratch verifier. The full suite
was not run. No installed client, real client config, live Uoink data, or real
token/key file was used. No request was made to `127.0.0.1:5179`. The guard
recorded zero violations. Windows and Mac output was tested on Windows using
temporary homes and fake bundles; this does not claim Mac runtime acceptance.
