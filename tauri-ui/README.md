# Uoink Tauri Shell Prototype

This is the v2.3 shell prototype: Tauri owns the custom installer UX and
hands off file operations to the existing Inno installer in silent mode.

What this proves:

- Custom title bar and brand-accurate installer screens.
- Four-step rail across the flow.
- Welcome, install location, ready, installing, migrating, and finished screens.
- Silent Inno invocation shape: `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR=...`.
- Native dashboard window launch pointed at `http://127.0.0.1:5179/dashboard`.

Run locally:

```powershell
cd tauri-ui
npm install
npm run tauri dev
```

Prototype limitation:

- `pick_install_dir` is stubbed in Rust. The UI accepts direct path edits now;
  the next implementation pass can wire Tauri's folder picker.
- Bundling is disabled in `tauri.conf.json`; this PR proves the shell and UI
  architecture before replacing the Inno-first release pipeline.
