# Uoink writing-surface ownership

Status: live Uoink behavior. This record prevents the suite split from
mistaking three overlapping modules for dead compatibility files.

## Live modules

`writing_studio.py`, `voice_dna.py`, and `scripts.py` remain part of Uoink.
They back Uoink's in-app Writing Studio, Voice DNA guard, and P5 Script
Studio. Writer owns a separate drafting product; its existence does not turn
these Uoink modules into shims.

The current call graph is executable:

- `server.py` imports all three modules at startup. Its authenticated HTTP
  handlers call the script surface around `server.py:9815-9947` and the
  writing surface around `server.py:10694-11055`.
- `uoink_mcp_tools.py` imports the same modules for 12 registered tools:
  `generate_script`, `revise_script`, `get_shot_list`, `list_scripts`,
  `get_script`, `write_tweet`, `write_blog`, `list_writing_pieces`,
  `get_writing_piece`, `add_style_anchor`, `list_style_anchors`, and
  `remove_style_anchor`.
- `writing_studio.py` imports `voice_dna.py`. `scripts.py` imports
  `writing_studio.py` when it assembles shared hook-lens grounding.
- `build.ps1:409-411` copies all three source modules into installer staging.
  The staging directory is generated build output, so the ownership banner
  belongs in the source modules and is carried into each build.

## Safe boundary

This change documents ownership only. It does not deprecate a tool, hide a
route, move data, or alter behavior.

Removing the modules is a separate product decision. If Ryan decides Uoink
should no longer write, the implementation must remove the HTTP handlers,
the 12 MCP registrations and handlers, dashboard callers, settings, installer
entries, and tests as one reviewed change. It must also define what happens to
existing writing records while preserving applied migration history. The
Uoink suite, installer gate, and family suite-smoke must then pass on the same
head. Until that decision exists, the modules stay live.
