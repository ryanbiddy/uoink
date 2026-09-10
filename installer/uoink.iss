; Uoink -- Inno Setup script.
;
; Built by ../build.ps1, which stages all files under installer\staging\
; before invoking ISCC against this script. ISCC writes the final
; Uoink-Setup-<version>.exe into ../build/.
;
; Layout of the installed product (under {app} = %LOCALAPPDATA%\Uoink):
;   python\           Python 3.11 embeddable + Lib\site-packages\yt_dlp
;   bin\              ffmpeg.exe + ffprobe.exe (PATH-prepended by server.py)
;   server.py         The local helper server. pythonw.exe runs it (no console).
;   index.py          SQLite library-index module imported by server.py.
;   migrate_install.py  One-time Yoink->Uoink first-run install migration.
;   migrations\       NNNN_*.sql files applied by index._run_migrations at boot.
;   uoink_mcp.py      MCP stdio entry point for agent clients.
;   uoink_mcp_tools.py  Shared MCP tool registry.
;   yoink_mcp.py      Back-compat shim re-exporting uoink_mcp (removed in v3).
;   yt_extract.py     Helper module imported by server.py.
;   topics.json       Topic-folder routing rules.
;   skills\           Operator Skill + copyable system prompt.
;   assets\dashboard\ Helper-served local dashboard HTML.
;   stop-server.bat   Stops the server via the PID file written at startup.
;   uoink.ico         Used for shortcuts and the uninstaller.

#define AppName       "Uoink"
; build.ps1 rewrites AppVersion from helper/_version.py before compiling.
#define AppVersion    "3.8.0"
#define AppPublisher  "ReplayRyan"
#define AppURL        "https://uoink.app"

[Setup]
; v2.1 rename: a NEW AppId is generated so the Uoink product installs as its
; own entry rather than upgrading the old Yoink AppId in place -- the first-run
; helper (migrate_install.py) migrates the user's data, and the old Yoink
; install is left for its 7-day grace cleanup. Keep this fixed from v2.1 on.
AppId={code:GetInstallAppId}
UsePreviousLanguage=no
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
VersionInfoVersion={#AppVersion}.0
DefaultDirName={localappdata}\Uoink
DefaultGroupName=Uoink
DisableProgramGroupPage=no
PrivilegesRequired=lowest
OutputDir=..\build
OutputBaseFilename=Uoink-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Branded wizard bitmaps (Variant A magnet-U), regenerated each build by
; ../generate_bitmaps.py into installer/assets/. Compile-time only (baked into
; Setup.exe, not installed to {app}). 24-bit BMP per Inno's requirement.
WizardImageFile=staging\installer-assets\wizard-large-100.bmp,staging\installer-assets\wizard-large-125.bmp,staging\installer-assets\wizard-large-150.bmp,staging\installer-assets\wizard-large-200.bmp
WizardSmallImageFile=staging\installer-assets\wizard-small-100.bmp,staging\installer-assets\wizard-small-125.bmp,staging\installer-assets\wizard-small-150.bmp,staging\installer-assets\wizard-small-200.bmp
SetupIconFile=staging\uoink.ico
UninstallDisplayIcon={app}\uoink.ico
UninstallDisplayName={code:GetUninstallDisplayName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Ordinary upgrades keep force-close. Isolated mode cannot disable Restart
; Manager by skipping wpPreparing (Inno never calls ShouldSkipPage for that
; page) or by leaving RegisterExtraCloseApplicationsResources empty (that
; callback only adds resources). Isolated setup must pass the documented
; /NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS switches and must refuse
; /CLOSEAPPLICATIONS, /FORCECLOSEAPPLICATIONS and /RESTARTAPPLICATIONS.
CloseApplications=force
ChangesEnvironment=no

[Messages]
; Net-new copy (WIZARD-COPY-AND-BITMAPS.md s1) to land the Uoink voice on the
; otherwise-stock Inno screens. ASCII-safe punctuation only (no em-dashes) so
; the strings render identically regardless of the .iss code page.
WelcomeLabel2=Uoink keeps videos, podcasts, and articles on your own disk, then hands them to your AI as a cited corpus you can write from.%n%nThis installer places the private local helper onto your machine. No accounts, no cloud dependencies. Setup completes in under a minute.
SelectDirDesc=Choose where to place Uoink's local files
SelectDirLabel3=Uoink runs a lightweight program on your computer to process source transcripts, screenshots, and article text locally, keeping your research private. Setup will install these tools into the folder below.
ReadyLabel1=Uoink is ready to set up on your machine. Click Install to place the local helper and dependencies in:
StatusExtractFiles=Placing local helper files and media dependencies...
FinishedHeadingLabel=Uoink is Ready
FinishedLabelNoIcons=Uoink has been successfully installed. The Uoink window will walk you through loading the browser button, then your first save opens the dashboard with the source ready to read.
FinishedLabel=Uoink has been successfully installed. The Uoink window will walk you through loading the browser button, then your first save opens the dashboard with the source ready to read.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Optional desktop shortcut (checked by default). The matching [Icons] entry
; below is gated on this task so users who uncheck it get no desktop icon.
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
; Python embeddable distribution (already includes pythonw.exe + python.exe
; + the stdlib zip). After staging, Lib\site-packages contains yt_dlp,
; WhisperX, and their runtime dependencies.
Source: "staging\python\*"; DestDir: "{app}\python"; Flags: recursesubdirs ignoreversion createallsubdirs

; Bundled binaries -- prepended to PATH at runtime by server.py.
Source: "staging\bin\*"; DestDir: "{app}\bin"; Flags: recursesubdirs ignoreversion

; Server source.
Source: "staging\server.py"; DestDir: "{app}"; Flags: ignoreversion
; System-tray module (Tier 1 v2.1.1) -- imported by server.py at boot on
; installed builds. Optional at runtime (degrades if pystray is unavailable).
Source: "staging\uoink_tray.py"; DestDir: "{app}"; Flags: ignoreversion
; Tier 2 GUI: pywebview splash + dashboard window subprocess entrypoints. The
; tray's left-click spawns uoink_dashboard.py; server.py spawns uoink_splash.py
; on the first boot. Optional at runtime (graceful degradation if pywebview
; or WebView2 Runtime is unavailable).
Source: "staging\uoink_splash.py";    DestDir: "{app}"; Flags: ignoreversion
Source: "staging\uoink_dashboard.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\index.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\clips.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\provenance.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\library_cards.py"; DestDir: "{app}"; Flags: ignoreversion
; Living Library Phase 2 work-queue service. uoink_mcp_tools.py imports it
; lazily; the installed helper must find it beside the other modules.
Source: "staging\library_work.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\source_subscriptions.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\library_analysis.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\library_resources.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\library_prompts.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\library_briefs.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\library_mirror.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\library_mirror_vault_io.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\library_media.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\library_faithfulness.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\usage_meter.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\uoink.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\uoink"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\scripts\install-watchdog.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "staging\scripts\recall_hook.py"; DestDir: "{app}\scripts"; Flags: ignoreversion
; Cross-platform path/OS helpers -- server.py and migrate_install.py import
; this at module top. Omitting it crashes the helper before it binds the port.
Source: "staging\_platform.py"; DestDir: "{app}"; Flags: ignoreversion
; Isolated installed-profile configuration. server.py, uoink_mcp.py, the
; splash/dashboard wrappers and the isolated stop command import this before
; opening default data. Must ship or isolated mode cannot start.
Source: "staging\uoink_install_isolation.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\migrate_install.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\channels.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\workspaces.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\claims.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\scripts.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\voice_dna.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\writing_studio.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\corpus_contract.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\corpus_provider.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\corpus_intelligence.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\writer_peer.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\engagement_contract.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\media_handoff.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\suite_service.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\page_extractor.py"; DestDir: "{app}"; Flags: ignoreversion
; v3.2.1/v3.3 modules imported by server.py at boot. These must be in both
; build.ps1 staging and Inno's installed file list; staging-only coverage is
; not enough because the real helper imports from {app}.
Source: "staging\source_manifest.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\openapi_bridge.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\reddit_extractor.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\taste_scoring.py"; DestDir: "{app}"; Flags: ignoreversion
; U-15 X text/thread capture. server.py imports x_extractor at module top, so it
; MUST be in Inno's installed file list too -- build.ps1 staging coverage alone is
; not enough. Its absence here is why v3.2.6 shipped without it and the helper
; crashed on launch with ModuleNotFoundError: No module named 'x_extractor'.
Source: "staging\x_extractor.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\x_article_extractor.py"; DestDir: "{app}"; Flags: ignoreversion
; Context-layer item 1: quick notes capture. server.py imports notes at module
; top, so it must be installed too or the helper crashes on launch.
Source: "staging\notes.py"; DestDir: "{app}"; Flags: ignoreversion
; Context-layer item 3: image / meme capture. server.py imports images at
; module top, so it must be installed too or the helper crashes on launch.
Source: "staging\images.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\memory_layer.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\podcasts.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\mobile_playlists.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\whisper_runner.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\uoink_mcp.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\uoink_mcp_tools.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\uoink_reliability.py"; DestDir: "{app}"; Flags: ignoreversion
; Back-compat shim so existing MCP client configs that still launch
; yoink_mcp.py keep working through the v2.x alias window (removed in v3).
Source: "staging\yoink_mcp.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\yt_extract.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\topics.json"; DestDir: "{app}"; Flags: ignoreversion
; VERSION is read by server.py at import (_read_version). build.ps1 stages it
; but the installer must also copy it into {app}, or the helper crashes on a
; clean install before binding the port.
Source: "staging\VERSION"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\helper\*"; DestDir: "{app}\helper"; Flags: recursesubdirs ignoreversion createallsubdirs
; Sprint 21: uoink_core/ package (modules split out of server.py). server.py
; imports it at module top -- must ship or the helper crashes before binding.
Source: "staging\uoink_core\*"; DestDir: "{app}\uoink_core"; Flags: recursesubdirs ignoreversion createallsubdirs
Source: "staging\skills\*"; DestDir: "{app}\skills"; Flags: recursesubdirs ignoreversion createallsubdirs
; v3.2 Writing Studio: ship the canonical Voice DNA doc so voice_dna.py
; can load VOICE_DNA_PROMPT at boot.
Source: "staging\voice_dna\*"; DestDir: "{app}\voice_dna"; Flags: recursesubdirs ignoreversion createallsubdirs
Source: "staging\assets\dashboard\*"; DestDir: "{app}\assets\dashboard"; Flags: ignoreversion recursesubdirs createallsubdirs
; Tier 2 GUI assets: splash HTML (served at /splash, wrapped by uoink_splash.py)
; and the shared brand-tokens stylesheet both pages consume.
Source: "staging\assets\splash\*"; DestDir: "{app}\assets\splash"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "staging\assets\brand\*";  DestDir: "{app}\assets\brand";  Flags: ignoreversion recursesubdirs createallsubdirs
; v3.1.3: unpacked Chrome extension. Chrome still requires user-controlled
; "Load unpacked"; the first-run splash points at this installed folder.
Source: "staging\extension\*"; DestDir: "{app}\extension"; Flags: ignoreversion recursesubdirs createallsubdirs
; v2.2.0: canonical rust-U mark loaded by the tray glyph (uoink_tray._image
; reads {app}\assets\logo-mark-color.png at start) so the tray icon and the
; installer .ico render the same artwork from the same source PNG.
Source: "staging\assets\logo-mark-color.png"; DestDir: "{app}\assets"; Flags: ignoreversion
; Library-index migrations -- index._run_migrations applies these at boot.
; Sprint 19.6 / Fix 1: pre-Sprint-19.6 installers omitted these, causing
; the helper to crash with "no such table: schema_version" on first launch.
Source: "staging\migrations\*"; DestDir: "{app}\migrations"; Flags: recursesubdirs ignoreversion createallsubdirs
; v3.2.3: curated default style anchors, seeded on first run by
; server._seed_default_style_anchors. Same bundle discipline as the v3.2.1
; module fix -- staging coverage alone is not enough; the file must land in
; {app}\defaults or the seed silently no-ops. verify_install.ps1 asserts it.
Source: "staging\defaults\*"; DestDir: "{app}\defaults"; Flags: recursesubdirs ignoreversion createallsubdirs
Source: "staging\stop-server.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\stop-server.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\verify_install.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\uoink.ico"; DestDir: "{app}"; Flags: ignoreversion

; v2.2.0 upgrade-prep PowerShell. Flags: dontcopy keeps it out of {app} --
; ExtractTemporaryFile() drops it into {tmp} during PrepareToInstall, runs
; it once, and the wizard's normal {tmp} cleanup deletes it after.
Source: "staging\upgrade_prep.ps1"; Flags: dontcopy

[Icons]
; The launcher entry is plain "Uoink" (not "Uoink Server") -- users don't
; think in servers, and this matches the README + finish-page wording.
Name: "{group}\Uoink"; \
  Filename: "{app}\python\pythonw.exe"; \
  Parameters: """{app}\server.py"" --show-dashboard"; \
  WorkingDir: "{app}"; \
  IconFilename: "{app}\uoink.ico"; \
  Comment: "Start Uoink"; \
  Check: not IsolatedInstall

Name: "{group}\Uoink Isolated"; \
  Filename: "{app}\python\pythonw.exe"; \
  Parameters: """{app}\server.py"" --isolated-profile ""{param:PROFILE}"" --isolated-port {param:PORT} --show-dashboard"; \
  WorkingDir: "{app}"; \
  IconFilename: "{app}\uoink.ico"; \
  Comment: "Start isolated Uoink"; \
  Check: IsolatedInstall

Name: "{group}\Stop Uoink"; \
  Filename: "{app}\stop-server.bat"; \
  WorkingDir: "{app}"; \
  IconFilename: "{app}\uoink.ico"; \
  Comment: "Stop Uoink"; \
  Check: not IsolatedInstall

Name: "{group}\Stop Uoink Isolated"; \
  Filename: "{app}\python\python.exe"; \
  Parameters: """{app}\uoink_install_isolation.py"" --isolated-stop --isolated-from-install-dir ""{app}"""; \
  WorkingDir: "{app}"; \
  IconFilename: "{app}\uoink.ico"; \
  Comment: "Stop isolated Uoink"; \
  Check: IsolatedInstall

Name: "{group}\Open Uoink folder"; \
  Filename: "{app}"; \
  IconFilename: "{app}\uoink.ico"; \
  Comment: "Open the Uoink install folder"; \
  Check: not IsolatedInstall

Name: "{group}\Open Uoink Isolated folder"; \
  Filename: "{app}"; \
  IconFilename: "{app}\uoink.ico"; \
  Comment: "Open the isolated Uoink install folder"; \
  Check: IsolatedInstall

Name: "{group}\Uninstall Uoink"; \
  Filename: "{uninstallexe}"; \
  Check: not IsolatedInstall

Name: "{group}\Uninstall Uoink Isolated"; \
  Filename: "{uninstallexe}"; \
  Check: IsolatedInstall

; Desktop launcher -- mirrors the {group}\Uoink start-menu entry above, gated on
; the optional "desktopicon" task. v3.2.7: the installer had promised a desktop
; shortcut but never created one.
Name: "{autodesktop}\Uoink"; \
  Filename: "{app}\python\pythonw.exe"; \
  Parameters: """{app}\server.py"" --show-dashboard"; \
  WorkingDir: "{app}"; \
  IconFilename: "{app}\uoink.ico"; \
  Comment: "Start Uoink"; \
  Tasks: desktopicon; \
  Check: not IsolatedInstall

Name: "{autodesktop}\Uoink Isolated"; \
  Filename: "{app}\python\pythonw.exe"; \
  Parameters: """{app}\server.py"" --isolated-profile ""{param:PROFILE}"" --isolated-port {param:PORT} --show-dashboard"; \
  WorkingDir: "{app}"; \
  IconFilename: "{app}\uoink.ico"; \
  Comment: "Start isolated Uoink"; \
  Tasks: desktopicon; \
  Check: IsolatedInstall

[Registry]
; Auto-start the helper on every Windows login. uninsdeletevalue removes the
; entry on uninstall so we don't leave dead Run keys behind. The first-run
; helper (migrate_install.py) drops any legacy "Yoink" Run value.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "Uoink"; \
  ValueData: """{app}\python\pythonw.exe"" ""{app}\server.py"""; \
  Flags: uninsdeletevalue; \
  Check: not IsolatedInstall

[Run]
; "Set up the browser button now" checkbox on the finish page (default checked).
Filename: "{app}\python\pythonw.exe"; \
  Parameters: """{app}\server.py"""; \
  WorkingDir: "{app}"; \
  Description: "Set up the browser button now"; \
  Flags: postinstall nowait skipifsilent; \
  Check: not IsolatedInstall

[UninstallRun]
; Stop a running server before file removal so unins doesn't fail on locked
; site-packages files. waituntilterminated gives the process time to exit.
Filename: "{app}\stop-server.bat"; \
  WorkingDir: "{app}"; \
  Flags: runhidden waituntilterminated; \
  RunOnceId: "StopUoink"; \
  Check: not IsolatedInstall

Filename: "{app}\python\python.exe"; \
  Parameters: """{app}\uoink_install_isolation.py"" --isolated-stop --isolated-from-install-dir ""{app}"""; \
  WorkingDir: "{app}"; \
  Flags: runhidden waituntilterminated; \
  RunOnceId: "StopIsolatedUoink"; \
  Check: IsolatedInstall

[UninstallDelete]
; Pip and the running Python create files we didn't ship (.pyc caches, the
; PID file, the live log). Sweep the whole install dir on uninstall.
Type: files; Name: "{app}\server.log"
Type: files; Name: "{app}\server.pid"
Type: files; Name: "{app}\isolated-install.json"
Type: filesandordirs; Name: "{app}\python\Lib\site-packages\__pycache__"
Type: filesandordirs; Name: "{app}\python\Lib\site-packages"
Type: filesandordirs; Name: "{app}\python\__pycache__"

[Code]
{ Tier 2 GUI wizard customization (DESIGN-MOCKS-tier-2.pdf, section 1.2). What's
  in scope for v2.2 within Inno's modern-wizard ceiling:
    * Branded WizardImageFile + WizardSmallImageFile (magnet-U Variant A)
    * AG-voiced [Messages] copy on the standard Welcome/Ready/Installing/Finished
    * A custom CreateCustomPage Welcome (the local-corpus hero from mock
      1.2.1) which replaces the stock welcome (wpWelcome is skipped).
    * A custom CreateCustomPage "Migrating Yoink Data" page (mock 1.2.5)
      shown only when a legacy %LOCALAPPDATA%\Yoink\ is detected. The actual
      migration runs on the helper's first boot (copy-not-move, 7-day grace),
      so this page sets expectations rather than tracking live progress.
  What is NOT in scope for v2.2 (flagged in PR for v2.3 Tauri shell):
    * Custom title-bar chrome (Inno owns the OS chrome).
    * Inline italic vermillion runs inside a headline (Inno labels don't do
      mid-line style mixing; the hero renders as a single rust-on-cream label
      that passes AA at large-text 18pt+).
    * JetBrains-Mono live-log inset on the Installing page.
    * "Close Yoink first" interstitial that detects a locked index.db during
      install -- migration runs post-wizard, so the wizard can't observe it.
  Pixel-target match for these requires a custom shell + a runnable helper to
  observe. Human visual QA is the gate before tagging v2.2. }

const
  { Inno TColor uses BGR hex (low byte = blue). #C2410C => $0C 41 C2. }
  C_RUST  = $000C41C2;
  C_CREAM = $00ECF4FF;
  C_INK   = $000A0A0A;
  ISOLATED_MARKER_MAX = 8192;

var
  WelcomePage:  TWizardPage;
  MigratePage:  TWizardPage;
  MigrateText:  TNewStaticText;
  DefaultNextCaption: String;
  DefaultNextLeft: Integer;
  DefaultNextWidth: Integer;
  IsolatedErrorText: String;

function IsolatedCmdToken(const Param: String; var Name, Value: String; var HasValue: Boolean): Boolean;
var
  S: String;
  Eq: Integer;
begin
  Result := False;
  Name := '';
  Value := '';
  HasValue := False;
  S := Trim(Param);
  if (Length(S) < 2) or (S[1] <> '/') then
    Exit;
  S := Copy(S, 2, Length(S));
  Eq := Pos('=', S);
  if Eq > 0 then
  begin
    Name := Copy(S, 1, Eq - 1);
    Value := RemoveQuotes(Copy(S, Eq + 1, Length(S)));
    HasValue := True;
  end
  else
    Name := S;
  Result := Name <> '';
end;

function IsolatedCountSwitch(const Wanted: String): Integer;
var
  I: Integer;
  Name, Value: String;
  HasValue: Boolean;
begin
  Result := 0;
  for I := 1 to ParamCount do
  begin
    if IsolatedCmdToken(ParamStr(I), Name, Value, HasValue) then
    begin
      if CompareText(Name, Wanted) = 0 then
        Result := Result + 1;
    end;
  end;
end;

function IsolatedCmdSwitchPresent(const Wanted: String): Boolean;
begin
  Result := IsolatedCountSwitch(Wanted) > 0;
end;

function IsolatedSingleSwitch(const Wanted: String; RequireValue: Boolean): Boolean;
var
  I: Integer;
  Name, Value: String;
  HasValue: Boolean;
begin
  Result := False;
  if IsolatedCountSwitch(Wanted) <> 1 then
    Exit;
  for I := 1 to ParamCount do
    if IsolatedCmdToken(ParamStr(I), Name, Value, HasValue) then
      if CompareText(Name, Wanted) = 0 then
      begin
        Result := (HasValue = RequireValue) and ((not RequireValue) or (Value <> ''));
        Exit;
      end;
end;

function IsolatedSetupRequested(): Boolean;
begin
  Result := CompareText(Trim(ExpandConstant('{param:ISOLATED}')), '1') = 0;
end;

function IsolatedRequestPresent(): Boolean;
begin
  Result := IsolatedCmdSwitchPresent('ISOLATED') or
            IsolatedCmdSwitchPresent('PROFILE') or
            IsolatedCmdSwitchPresent('PORT');
end;

function IsolatedMarkerPath(const AppDir: String): String;
begin
  Result := AddBackslash(AppDir) + 'isolated-install.json';
end;

function IsolatedMarkerFileExists(const AppDir: String): Boolean;
begin
  Result := FileExists(IsolatedMarkerPath(AppDir));
end;

function IsolatedPersisted(): Boolean;
var
  Flag: String;
begin
  Result := False;
  if not IsUninstaller() then
    Exit;
  Flag := GetPreviousData('Isolated', '');
  Result := CompareText(Trim(Flag), '1') = 0;
end;

function IsolatedInstall(): Boolean;
begin
  if IsUninstaller() then
    Result := IsolatedPersisted()
  else
    Result := IsolatedSetupRequested();
end;

function GetInstallAppId(Param: String): String;
begin
  (* Ordinary AppId stays 1CCDA47D-2347-43D1-99F4-BD6E7C231288. Isolated
     installs register a distinct uninstall entry. *)
  if IsolatedSetupRequested() then
    Result := '{8F3E1B27-9C6A-4E5D-A2B8-7D4C1E0F93A5}'
  else
    Result := '{1CCDA47D-2347-43D1-99F4-BD6E7C231288}';
end;

function GetUninstallDisplayName(Param: String): String;
begin
  if IsolatedInstall() then
    Result := 'Uoink Isolated'
  else
    Result := '{#AppName}';
end;

function IsolatedProfile(): String;
begin
  Result := RemoveQuotes(Trim(ExpandConstant('{param:PROFILE}')));
end;

function IsolatedPort(): Integer;
begin
  Result := StrToIntDef(Trim(ExpandConstant('{param:PORT}')), -1);
end;

function IsolatedExplicitDir(): String;
begin
  Result := RemoveQuotes(Trim(ExpandConstant('{param:DIR}')));
end;

function JsonEscape(const S: String): String;
begin
  Result := S;
  StringChangeEx(Result, '\', '\\', True);
  StringChangeEx(Result, '"', '\"', True);
end;

function IsolatedNormalizedInput(const Path: String): String;
begin
  Result := RemoveQuotes(Trim(Path));
  StringChangeEx(Result, '/', '\', True);
end;

function IsolatedPathIsAbsolute(const Profile: String): Boolean;
var
  S: String;
begin
  S := IsolatedNormalizedInput(Profile);
  Result := False;
  if Length(S) >= 3 then
    Result := (S[2] = ':') and (S[3] = '\');
end;

function IsolatedPathLooksDeviceOrUnc(const Path: String): Boolean;
var
  S: String;
begin
  S := IsolatedNormalizedInput(Path);
  Result := (Length(S) >= 2) and (S[1] = '\') and (S[2] = '\');
end;

function IsolatedReservedName(const Component: String): Boolean;
var
  Upper, Base: String;
  Dot: Integer;
begin
  Upper := UpperCase(Trim(Component));
  while (Length(Upper) > 0) and ((Upper[Length(Upper)] = '.') or (Upper[Length(Upper)] = ' ')) do
    Upper := Copy(Upper, 1, Length(Upper) - 1);
  Dot := Pos('.', Upper);
  if Dot > 0 then
    Base := Copy(Upper, 1, Dot - 1)
  else
    Base := Upper;
  Result :=
    (Base = 'CON') or (Base = 'PRN') or (Base = 'AUX') or (Base = 'NUL') or
    (Base = 'COM1') or (Base = 'COM2') or (Base = 'COM3') or (Base = 'COM4') or
    (Base = 'COM5') or (Base = 'COM6') or (Base = 'COM7') or (Base = 'COM8') or
    (Base = 'COM9') or
    (Base = 'LPT1') or (Base = 'LPT2') or (Base = 'LPT3') or (Base = 'LPT4') or
    (Base = 'LPT5') or (Base = 'LPT6') or (Base = 'LPT7') or (Base = 'LPT8') or
    (Base = 'LPT9');
end;

function IsolatedPathIsAmbiguous(const Path: String): Boolean;
var
  S, Comp: String;
  I, Start: Integer;
  Ch: String;
begin
  S := IsolatedNormalizedInput(Path);
  Result := True;
  if (S = '') or (Length(S) > 4096) then
    Exit;
  I := 1;
  while I <= Length(S) do
  begin
    Ch := Copy(S, I, 1);
    if (Ch = '*') or (Ch = '?') or (Ch = '<') or (Ch = '>') or (Ch = '|') or (Ch = '"') then
      Exit;
    if (Ch = ':') and (I <> 2) then
      Exit;
    I := I + 1;
  end;
  if (Length(S) >= 3) and (S[2] = ':') and (S[3] = '\') then
    Start := 4
  else
    Exit;
  Comp := '';
  I := Start;
  while I <= Length(S) + 1 do
  begin
    if (I > Length(S)) or (S[I] = '\') then
    begin
      if Comp = '' then
      begin
        if I <= Length(S) then
          Exit;
      end
      else
      begin
        if (Comp[Length(Comp)] = '.') or (Comp[Length(Comp)] = ' ') then
          Exit;
        if IsolatedReservedName(Comp) then
          Exit;
      end;
      Comp := '';
    end
    else
      Comp := Comp + S[I];
    I := I + 1;
  end;
  Result := False;
end;

function IsolatedWinLongPath(ShortPathName, LongPathName: String; cchBuffer: Integer): Integer;
external 'GetLongPathNameW@kernel32.dll stdcall';

function IsolatedWinGetFileAttributes(PathName: String): Integer;
external 'GetFileAttributesW@kernel32.dll stdcall';

function IsolatedWinCreateFile(
  FileName: String;
  DesiredAccess, ShareMode, SecurityAttributes: Integer;
  CreationDisposition, FlagsAndAttributes, TemplateFile: Integer): Integer;
external 'CreateFileW@kernel32.dll stdcall';

function IsolatedWinCloseHandle(Handle: Integer): Integer;
external 'CloseHandle@kernel32.dll stdcall';

function IsolatedWinFinalPath(
  Handle: Integer; FilePath: String; cchFilePath, Flags: Integer): Integer;
external 'GetFinalPathNameByHandleW@kernel32.dll stdcall';

function IsolatedExpandOnly(const Path: String): String;
var
  S: String;
begin
  S := IsolatedNormalizedInput(Path);
  if S <> '' then
    S := ExpandFileName(S);
  Result := RemoveBackslashUnlessRoot(S);
end;

function IsolatedExistingAncestorsHaveReparse(const Path: String): Boolean;
var
  Current: String;
  Attr: Integer;
begin
  Result := False;
  Current := IsolatedExpandOnly(Path);
  while Length(Current) >= 3 do
  begin
    Attr := IsolatedWinGetFileAttributes(Current);
    if Attr <> -1 then
    begin
      if (Attr and FILE_ATTRIBUTE_REPARSE_POINT) <> 0 then
      begin
        Result := True;
        Exit;
      end;
    end;
    if (Length(Current) <= 3) and (Current[2] = ':') then
      Break;
    Current := RemoveBackslashUnlessRoot(ExtractFileDir(Current));
    if Current = '' then
      Break;
  end;
end;

function IsolatedFinalPath(const Path: String): String;
var
  Current, Buf: String;
  Handle, N: Integer;
begin
  Result := '';
  Current := IsolatedExpandOnly(Path);
  while (Current <> '') and (not DirExists(Current)) and (not FileExists(Current)) do
  begin
    if (Length(Current) <= 3) and (Length(Current) >= 2) and (Current[2] = ':') then
      Break;
    Current := RemoveBackslashUnlessRoot(ExtractFileDir(Current));
  end;
  if (Current = '') or ((not DirExists(Current)) and (not FileExists(Current))) then
    Exit;
  Handle := IsolatedWinCreateFile(Current, 0, 7, 0, 3, $02000000, 0);
  if (Handle = 0) or (Handle = -1) then
    Exit;
  try
    SetLength(Buf, 4096);
    try
      N := IsolatedWinFinalPath(Handle, Buf, 4096, 0);
    except
      N := 0;
    end;
    if (N > 0) and (N < 4096) then
      Result := Copy(Buf, 1, N);
  finally
    IsolatedWinCloseHandle(Handle);
  end;
  if CompareText(Copy(Result, 1, 8), '\\?\UNC\') = 0 then
    Result := '\' + Copy(Result, 8, Length(Result))
  else if CompareText(Copy(Result, 1, 4), '\\?\') = 0 then
    Result := Copy(Result, 5, Length(Result));
end;

function IsolatedCanonicalPath(const Path: String): String;
var
  S, Buf: String;
  N: Integer;
begin
  S := IsolatedNormalizedInput(Path);
  if S <> '' then
    S := ExpandFileName(S);
  SetLength(Buf, 4096);
  N := IsolatedWinLongPath(S, Buf, 4096);
  if (N > 0) and (N < 4096) then
    S := Copy(Buf, 1, N);
  Result := UpperCase(RemoveBackslashUnlessRoot(S));
end;

function IsolatedPathIsRootVolume(const Profile: String): Boolean;
var
  S: String;
begin
  S := IsolatedCanonicalPath(Profile);
  Result := (Length(S) = 3) and (S[2] = ':') and (S[3] = '\');
end;

function IsolatedSamePath(const Left, Right: String): Boolean;
var
  A, B, SA, SB: String;
begin
  A := IsolatedCanonicalPath(Left);
  B := IsolatedCanonicalPath(Right);
  Result := CompareText(A, B) = 0;
  if Result then
    Exit;
  SA := GetShortName(A);
  SB := GetShortName(B);
  if (SA <> '') and (SB <> '') then
    Result := CompareText(SA, SB) = 0;
end;

function IsolatedPathIsInside(const Inner, Outer: String): Boolean;
var
  A, B: String;
begin
  if IsolatedSamePath(Inner, Outer) then
  begin
    Result := True;
    Exit;
  end;
  A := IsolatedCanonicalPath(Inner);
  B := AddBackslash(IsolatedCanonicalPath(Outer));
  Result := (Length(A) > Length(B)) and (Copy(A, 1, Length(B)) = B);
end;

procedure IsolatedAbort(const CodeAndMessage: String);
begin
  IsolatedErrorText := CodeAndMessage;
  Log('isolated install refused: ' + CodeAndMessage);
  if not WizardSilent then
    MsgBox(CodeAndMessage, mbError, MB_OK);
end;

procedure IsolatedUninstallAbort(const CodeAndMessage: String);
begin
  IsolatedErrorText := CodeAndMessage;
  Log('isolated uninstall refused: ' + CodeAndMessage);
  if not UninstallSilent then
    MsgBox(CodeAndMessage, mbError, MB_OK);
end;

function IsolatedCloseSwitchesValid(): Boolean;
begin
  Result := False;
  if IsolatedCmdSwitchPresent('CLOSEAPPLICATIONS') or
     IsolatedCmdSwitchPresent('FORCECLOSEAPPLICATIONS') or
     IsolatedCmdSwitchPresent('RESTARTAPPLICATIONS') then
  begin
    IsolatedAbort('isolated-close-applications-forbidden: isolated mode refuses /CLOSEAPPLICATIONS, /FORCECLOSEAPPLICATIONS and /RESTARTAPPLICATIONS');
    Exit;
  end;
  if (not IsolatedSingleSwitch('NOCLOSEAPPLICATIONS', False)) or
     (not IsolatedSingleSwitch('NORESTARTAPPLICATIONS', False)) then
  begin
    IsolatedAbort('isolated-close-applications-required: isolated mode requires /NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS');
    Exit;
  end;
  Result := True;
end;

function IsolatedJsonSkipWs(const Body: String; I: Integer): Integer;
begin
  while (I <= Length(Body)) and ((Body[I] = ' ') or (Body[I] = #9) or (Body[I] = #10) or (Body[I] = #13)) do
    I := I + 1;
  Result := I;
end;

function IsolatedJsonParseString(const Body: String; var I: Integer; var Value: String): Boolean;
var
  Escaping: Boolean;
begin
  Result := False;
  Value := '';
  if (I > Length(Body)) or (Body[I] <> '"') then
    Exit;
  I := I + 1;
  Escaping := False;
  while I <= Length(Body) do
  begin
    if Ord(Body[I]) < 32 then
      Exit;
    if Escaping then
    begin
      if (Body[I] <> '\') and (Body[I] <> '"') then
        Exit;
      Value := Value + Body[I];
      Escaping := False;
    end
    else if Body[I] = '\' then
      Escaping := True
    else if Body[I] = '"' then
    begin
      I := I + 1;
      Result := True;
      Exit;
    end
    else
      Value := Value + Body[I];
    I := I + 1;
    if Length(Value) > 4096 then
      Exit;
  end;
end;

function IsolatedJsonParseInt(const Body: String; var I: Integer; var Value: Integer): Boolean;
var
  Digits: String;
  Start: Integer;
begin
  Result := False;
  Value := -1;
  if (I <= Length(Body)) and (Body[I] = '-') then
    Exit;
  if (I > Length(Body)) or (Body[I] < '0') or (Body[I] > '9') then
    Exit;
  if (Body[I] = '0') and (I < Length(Body)) and (Body[I + 1] >= '0') and (Body[I + 1] <= '9') then
    Exit;
  Start := I;
  while (I <= Length(Body)) and (Body[I] >= '0') and (Body[I] <= '9') do
    I := I + 1;
  if (I - Start) > 10 then
    Exit;
  Digits := Copy(Body, Start, I - Start);
  Value := StrToIntDef(Digits, -1);
  if (Value < 0) or (IntToStr(Value) <> Digits) then
    Exit;
  Result := True;
end;

function IsolatedParseMarker(
  const Body: String;
  var Mode, Profile, Host, AppDir: String;
  var Port: Integer): Boolean;
var
  I, Count, SeenMode, SeenProfile, SeenPort, SeenHost, SeenApp: Integer;
  Key, StrVal: String;
  IntVal: Integer;
  NeedComma: Boolean;
begin
  Result := False;
  Mode := '';
  Profile := '';
  Host := '';
  AppDir := '';
  Port := -1;
  if (Length(Body) = 0) or (Length(Body) > ISOLATED_MARKER_MAX) then
    Exit;
  I := IsolatedJsonSkipWs(Body, 1);
  if (I > Length(Body)) or (Body[I] <> '{') then
    Exit;
  I := I + 1;
  Count := 0;
  SeenMode := 0;
  SeenProfile := 0;
  SeenPort := 0;
  SeenHost := 0;
  SeenApp := 0;
  NeedComma := False;
  while True do
  begin
    I := IsolatedJsonSkipWs(Body, I);
    if I > Length(Body) then
      Exit;
    if Body[I] = '}' then
    begin
      I := I + 1;
      Break;
    end;
    if NeedComma then
    begin
      if Body[I] <> ',' then
        Exit;
      I := I + 1;
      I := IsolatedJsonSkipWs(Body, I);
      if (I <= Length(Body)) and (Body[I] = '}') then
        Exit;
    end;
    if not IsolatedJsonParseString(Body, I, Key) then
      Exit;
    I := IsolatedJsonSkipWs(Body, I);
    if (I > Length(Body)) or (Body[I] <> ':') then
      Exit;
    I := I + 1;
    I := IsolatedJsonSkipWs(Body, I);
    if I > Length(Body) then
      Exit;
    if (Body[I] = '{') or (Body[I] = '[') then
      Exit;
    if Body[I] = '"' then
    begin
      if not IsolatedJsonParseString(Body, I, StrVal) then
        Exit;
      if Key = 'mode' then
      begin
        SeenMode := SeenMode + 1;
        Mode := StrVal;
      end
      else if Key = 'profile' then
      begin
        SeenProfile := SeenProfile + 1;
        Profile := StrVal;
      end
      else if Key = 'host' then
      begin
        SeenHost := SeenHost + 1;
        Host := StrVal;
      end
      else if Key = 'app_dir' then
      begin
        SeenApp := SeenApp + 1;
        AppDir := StrVal;
      end
      else
        Exit;
    end
    else
    begin
      if not IsolatedJsonParseInt(Body, I, IntVal) then
        Exit;
      if Key = 'port' then
      begin
        SeenPort := SeenPort + 1;
        Port := IntVal;
      end
      else
        Exit;
    end;
    Count := Count + 1;
    if Count > 5 then
      Exit;
    NeedComma := True;
  end;
  I := IsolatedJsonSkipWs(Body, I);
  if I <= Length(Body) then
    Exit;
  if (SeenMode <> 1) or (SeenProfile <> 1) or (SeenPort <> 1) or
     (SeenHost <> 1) or (SeenApp <> 1) then
    Exit;
  if (Mode <> 'isolated') or (Profile = '') or (Host <> '127.0.0.1') or (AppDir = '') then
    Exit;
  if (Port < 1) or (Port > 65535) or (Port = 5179) then
    Exit;
  Result := True;
end;

function IsolatedJsonExtractString(const Body, Key: String; var Value: String): Boolean;
var
  Mode, Profile, Host, AppDir: String;
  Port: Integer;
begin
  Result := False;
  Value := '';
  if not IsolatedParseMarker(Body, Mode, Profile, Host, AppDir, Port) then
    Exit;
  if Key = 'mode' then
  begin
    Value := Mode;
    Result := True;
  end
  else if Key = 'profile' then
  begin
    Value := Profile;
    Result := True;
  end
  else if Key = 'host' then
  begin
    Value := Host;
    Result := True;
  end
  else if Key = 'app_dir' then
  begin
    Value := AppDir;
    Result := True;
  end;
end;

function IsolatedJsonExtractInt(const Body, Key: String; var Value: Integer): Boolean;
var
  Mode, Profile, Host, AppDir: String;
  Port: Integer;
begin
  Result := False;
  Value := -1;
  if not IsolatedParseMarker(Body, Mode, Profile, Host, AppDir, Port) then
    Exit;
  if Key = 'port' then
  begin
    Value := Port;
    Result := True;
  end;
end;

function IsolatedReadMarkerBody(const AppDir: String; var Body: String): Boolean;
var
  Raw: AnsiString;
begin
  Result := False;
  Body := '';
  if IsolatedPathLooksDeviceOrUnc(AppDir) or IsolatedExistingAncestorsHaveReparse(AppDir) or
     IsolatedExistingAncestorsHaveReparse(IsolatedMarkerPath(AppDir)) then
    Exit;
  if not LoadStringFromFile(IsolatedMarkerPath(AppDir), Raw) then
    Exit;
  if Length(Raw) > ISOLATED_MARKER_MAX then
    Exit;
  Body := Utf8Decode(Raw);
  if Utf8Encode(Body) <> Raw then
    Exit;
  Result := True;
end;

function IsolatedMarkerExact(const AppDir, Profile: String; Port: Integer): Boolean;
var
  Body, Mode, MarkedProfile, Host, AppDirMarked: String;
  MarkedPort: Integer;
begin
  Result := False;
  if not IsolatedReadMarkerBody(AppDir, Body) then
    Exit;
  if not IsolatedParseMarker(Body, Mode, MarkedProfile, Host, AppDirMarked, MarkedPort) then
    Exit;
  Result := IsolatedSamePath(MarkedProfile, Profile) and (MarkedPort = Port) and
            IsolatedSamePath(AppDirMarked, AppDir);
end;

function IsolatedMarkerMatches(const AppDir, Profile: String; Port: Integer): Boolean;
begin
  { Exact JSON field match; substring searches are not ownership. }
  Result := IsolatedMarkerExact(AppDir, Profile, Port);
end;

function IsolatedMarkerWellFormed(const AppDir: String): Boolean;
var
  Body, Mode, MarkedProfile, Host, AppDirMarked: String;
  MarkedPort: Integer;
begin
  Result := False;
  if not IsolatedReadMarkerBody(AppDir, Body) then
    Exit;
  Result := IsolatedParseMarker(Body, Mode, MarkedProfile, Host, AppDirMarked, MarkedPort);
end;

function IsolatedPathIsUnsafe(const Path: String): Boolean;
begin
  Result := IsolatedPathIsInside(Path, ExpandConstant('{win}')) or
            IsolatedPathIsInside(Path, ExpandConstant('{sys}')) or
            IsolatedPathIsInside(Path, ExpandConstant('{pf}')) or
            IsolatedPathIsInside(Path, ExpandConstant('{pf32}'));
end;

function IsolatedPathHitsLibrary(const Path: String; var Code: String): Boolean;
var
  NormalData, LegacyData, DesktopUoink, DesktopYoink: String;
begin
  Result := True;
  NormalData := ExpandConstant('{localappdata}\Uoink');
  LegacyData := ExpandConstant('{localappdata}\Yoink');
  DesktopUoink := ExpandConstant('{userdesktop}\Uoink');
  DesktopYoink := ExpandConstant('{userdesktop}\Yoink');
  if IsolatedPathIsInside(Path, NormalData) or IsolatedPathIsInside(NormalData, Path) then
  begin
    Code := 'isolated-profile-normal-data';
    Exit;
  end;
  if IsolatedPathIsInside(Path, LegacyData) or IsolatedPathIsInside(LegacyData, Path) then
  begin
    Code := 'isolated-profile-legacy-data';
    Exit;
  end;
  if IsolatedPathIsInside(Path, DesktopUoink) or IsolatedPathIsInside(DesktopUoink, Path) or
     IsolatedPathIsInside(Path, DesktopYoink) or IsolatedPathIsInside(DesktopYoink, Path) then
  begin
    Code := 'isolated-profile-normal-data';
    Exit;
  end;
  Result := False;
  Code := '';
end;

function IsolatedGuardPath(const Path, Kind: String): Boolean;
var
  LibraryCode, Resolved: String;
begin
  Result := False;
  if IsolatedPathLooksDeviceOrUnc(Path) then
  begin
    IsolatedAbort('isolated-path-unsupported: isolated ' + Kind + ' cannot be a device or UNC path');
    Exit;
  end;
  if IsolatedPathIsAmbiguous(Path) then
  begin
    IsolatedAbort('isolated-path-unsupported: isolated ' + Kind + ' has an ambiguous Windows path');
    Exit;
  end;
  if IsolatedExistingAncestorsHaveReparse(Path) then
  begin
    IsolatedAbort('isolated-path-reparse: isolated ' + Kind + ' refuses a reparse point in any existing ancestor');
    Exit;
  end;
  Resolved := IsolatedFinalPath(Path);
  if Resolved = '' then
  begin
    IsolatedAbort('isolated-path-unresolved: isolated ' + Kind + ' cannot verify its existing ancestor');
    Exit;
  end;
  if (Resolved <> '') and IsolatedPathLooksDeviceOrUnc(Resolved) then
  begin
    IsolatedAbort('isolated-path-unsupported: isolated ' + Kind + ' resolves to a device or UNC path');
    Exit;
  end;
  if (Resolved <> '') and IsolatedPathHitsLibrary(Resolved, LibraryCode) then
  begin
    IsolatedAbort(LibraryCode + ': isolated ' + Kind + ' resolves through an alias onto ordinary or legacy data');
    Exit;
  end;
  Result := True;
end;

function IsolatedValidateProfile(const Profile: String): Boolean;
var
  LibraryCode: String;
begin
  Result := False;
  if Profile = '' then
  begin
    IsolatedAbort('isolated-profile-missing: isolated mode requires /PROFILE=<absolute directory>');
    Exit;
  end;
  if IsolatedPathLooksDeviceOrUnc(Profile) then
  begin
    IsolatedAbort('isolated-path-unsupported: isolated /PROFILE cannot be a device or UNC path');
    Exit;
  end;
  if not IsolatedPathIsAbsolute(Profile) then
  begin
    IsolatedAbort('isolated-profile-relative: isolated /PROFILE must be an absolute directory');
    Exit;
  end;
  if not IsolatedGuardPath(Profile, '/PROFILE') then
    Exit;
  if IsolatedPathIsRootVolume(Profile) then
  begin
    IsolatedAbort('isolated-profile-root-volume: isolated /PROFILE cannot be a drive root');
    Exit;
  end;
  if IsolatedPathIsUnsafe(Profile) then
  begin
    IsolatedAbort('isolated-profile-unsafe: isolated /PROFILE cannot be a protected system path');
    Exit;
  end;
  if IsolatedPathHitsLibrary(Profile, LibraryCode) then
  begin
    IsolatedAbort(LibraryCode + ': isolated /PROFILE collides with ordinary or legacy data');
    Exit;
  end;
  if not DirExists(Profile) then
  begin
    IsolatedAbort('isolated-profile-not-found: isolated /PROFILE must already exist');
    Exit;
  end;
  Result := True;
end;

function IsolatedValidatePortValue(Port: Integer): Boolean;
begin
  Result := False;
  if Trim(ExpandConstant('{param:PORT}')) = '' then
  begin
    IsolatedAbort('isolated-port-missing: isolated mode requires /PORT=<loopback port>');
    Exit;
  end;
  if Port < 1 then
  begin
    IsolatedAbort('isolated-port-invalid: isolated /PORT must be an integer 1-65535');
    Exit;
  end;
  if Port > 65535 then
  begin
    IsolatedAbort('isolated-port-invalid: isolated /PORT must be an integer 1-65535');
    Exit;
  end;
  if Port = 5179 then
  begin
    IsolatedAbort('isolated-port-forbidden: isolated /PORT cannot be 5179');
    Exit;
  end;
  Result := True;
end;

function IsolatedValidateTargetDir(const AppDir: String): Boolean;
var
  Profile: String;
  Port: Integer;
  LibraryCode: String;
begin
  Result := False;
  if not IsolatedSetupRequested() then
  begin
    if IsolatedMarkerFileExists(AppDir) then
    begin
      IsolatedAbort('isolated-install-ordinary-reuse: ordinary setup refuses an isolated target before preparation');
      Exit;
    end;
    Result := True;
    Exit;
  end;
  Profile := IsolatedProfile();
  Port := IsolatedPort();
  if AppDir = '' then
  begin
    IsolatedAbort('isolated-install-app-relative: isolated /DIR must be an absolute directory');
    Exit;
  end;
  if IsolatedPathLooksDeviceOrUnc(AppDir) then
  begin
    IsolatedAbort('isolated-path-unsupported: isolated /DIR cannot be a device or UNC path');
    Exit;
  end;
  if not IsolatedPathIsAbsolute(AppDir) then
  begin
    IsolatedAbort('isolated-install-app-relative: isolated /DIR must be an absolute directory');
    Exit;
  end;
  if not IsolatedGuardPath(AppDir, '/DIR') then
    Exit;
  if IsolatedPathIsRootVolume(AppDir) then
  begin
    IsolatedAbort('isolated-profile-root-volume: isolated /DIR cannot be a drive root');
    Exit;
  end;
  if IsolatedPathIsUnsafe(AppDir) then
  begin
    IsolatedAbort('isolated-profile-unsafe: isolated /DIR cannot be a protected system path');
    Exit;
  end;
  if IsolatedPathHitsLibrary(AppDir, LibraryCode) then
  begin
    IsolatedAbort('isolated-install-ordinary-reuse: isolated /DIR collides with ordinary or legacy data');
    Exit;
  end;
  if IsolatedSamePath(AppDir, ExpandConstant('{localappdata}\Uoink')) then
  begin
    IsolatedAbort('isolated-install-ordinary-reuse: isolated /DIR cannot be the ordinary install directory');
    Exit;
  end;
  if IsolatedSamePath(AppDir, Profile) or IsolatedPathIsInside(AppDir, Profile) or IsolatedPathIsInside(Profile, AppDir) then
  begin
    IsolatedAbort('isolated-profile-conflict: isolated /PROFILE cannot be the install directory');
    Exit;
  end;
  if IsolatedMarkerFileExists(AppDir) then
  begin
    if not IsolatedMarkerWellFormed(AppDir) then
    begin
      IsolatedAbort('isolated-install-marker-mismatch: existing isolated-install.json is damaged');
      Exit;
    end;
    if not IsolatedMarkerExact(AppDir, Profile, Port) then
    begin
      IsolatedAbort('isolated-install-marker-mismatch: existing isolated-install.json does not match /PROFILE and /PORT');
      Exit;
    end;
  end
  else if FileExists(AddBackslash(AppDir) + 'server.py') then
  begin
    IsolatedAbort('isolated-install-ordinary-reuse: refusing to treat an ordinary installation as isolated');
    Exit;
  end;
  Result := True;
end;

function IsolatedValidateDeclaredInputs(): Boolean;
var
  ExplicitDir: String;
begin
  Result := False;
  if (not IsolatedSingleSwitch('ISOLATED', True)) or
     (not IsolatedSingleSwitch('PROFILE', True)) or
     (not IsolatedSingleSwitch('PORT', True)) or
     (not IsolatedSingleSwitch('DIR', True)) then
  begin
    IsolatedAbort('isolated-argument-invalid: isolated mode requires one value each for /ISOLATED, /PROFILE, /PORT and /DIR');
    Exit;
  end;
  if not IsolatedValidateProfile(IsolatedProfile()) then
    Exit;
  if not IsolatedValidatePortValue(IsolatedPort()) then
    Exit;
  ExplicitDir := IsolatedExplicitDir();
  if ExplicitDir <> '' then
  begin
    if not IsolatedValidateTargetDir(ExplicitDir) then
      Exit;
  end;
  if FileExists(AddBackslash(IsolatedProfile()) + 'runtime-identity.json') then
  begin
    IsolatedAbort('isolated-running-requires-stop: owned isolated helper still recorded as running; run the isolated stop command first');
    Exit;
  end;
  Result := True;
end;

function InitializeSetup(): Boolean;
begin
  Result := False;
  IsolatedErrorText := '';
  if IsolatedRequestPresent() then
  begin
    if not IsolatedSetupRequested() then
    begin
      IsolatedAbort('isolated-argument-invalid: isolated mode requires /ISOLATED=1; missing or contradictory isolated parameters refuse ordinary setup');
      Exit;
    end;
    if IsolatedCountSwitch('ISOLATED') > 1 then
    begin
      IsolatedAbort('isolated-argument-invalid: duplicate /ISOLATED is contradictory');
      Exit;
    end;
    if not IsolatedCloseSwitchesValid() then
      Exit;
    Result := IsolatedValidateDeclaredInputs();
    Exit;
  end;
  Result := True;
end;

function LegacyYoinkPresent(): Boolean;
begin
  Result := DirExists(ExpandConstant('{localappdata}\Yoink'));
end;

procedure AddLabel(P: TWizardPage; const Caption: string;
                   Top, Height, FontSize: Integer; FontStyle: TFontStyles;
                   Colr: TColor);
var L: TNewStaticText;
begin
  L := TNewStaticText.Create(P);
  L.Parent := P.Surface;
  L.AutoSize := False;
  L.Left := ScaleX(0);
  L.Top := ScaleY(Top);
  L.Width := P.SurfaceWidth;
  L.Height := ScaleY(Height);
  L.Caption := Caption;
  L.Font.Size := FontSize;
  L.Font.Style := FontStyle;
  L.Font.Color := Colr;
  L.WordWrap := True;
end;

procedure BuildWelcomePage();
begin
  WelcomePage := CreateCustomPage(wpWelcome,
    'Welcome to Uoink',
    'Build a local corpus your AI can write from.');
  WelcomePage.Surface.Color := C_CREAM;
  { Hero (mock 1.2.1). Rust on the cream wizard ground passes AA for large
    text (>=18pt bold); body copy below stays on the default ink-on-cream the
    wizard uses -- never rust on ink, per the contrast rules. }
  AddLabel(WelcomePage, 'Build from receipts.',  20,  58, 28, [fsBold], C_RUST);
  AddLabel(WelcomePage,
    'Save videos, podcasts, articles, and threads into a cited corpus on your disk.',
                                               96, 42, 11, [], C_INK);
  AddLabel(WelcomePage,
    'This installs the local helper that does the work. ' +
    'No account, no cloud. Takes about a minute.',
                                              146, 48, 10, [], C_INK);
  AddLabel(WelcomePage,
    'MIT - open source - uoink.app',          218, 24,  9, [fsItalic], C_RUST);
end;

procedure BuildMigratePage();
begin
  // Keep legacy-folder details out of visible installer copy. The real
  // migration source path remains in logs and code, but the wizard text needs
  // to pass the strict user-facing brand audit.
  //
  // IN-12: anchor this after wpSelectDir, not wpReady, so the expectation-
  // setting note appears BEFORE the user commits on Ready. Anchoring it to
  // wpReady put another page of prose after the Install click. The page is
  // pure copy (migration itself runs on the helper's first boot), so its
  // position has no functional effect on the migration.
  MigratePage := CreateCustomPage(wpSelectDir, 'Migrating your previous install',
    'Moving your saved videos, settings, and API key safely into Uoink');
  MigrateText := TNewStaticText.Create(MigratePage);
  MigrateText.Parent := MigratePage.Surface;
  MigrateText.AutoSize := False;
  MigrateText.Left := 0;
  MigrateText.Top := 0;
  MigrateText.Width := MigratePage.SurfaceWidth;
  MigrateText.Height := MigratePage.SurfaceHeight;
  MigrateText.WordWrap := True;
  MigrateText.Caption :=
    'A previous install of the helper was found on this PC.' + #13#10#13#10 +
    'The first time Uoink starts, it will automatically copy your saved videos, ' +
    'settings, and Anthropic API key from the previous install. Nothing is moved ' +
    'or deleted until a fully verified copy exists -- your old files stay in place ' +
    'for 7 days as a safety net, then are removed automatically.' + #13#10#13#10 +
    'If anything cannot be copied automatically, no data is lost: your old files ' +
    'remain in the legacy local data folder, and you can re-enter your Anthropic API key ' +
    'from the Uoink Settings menu at any time.';
end;

procedure InitializeWizard();
begin
  DefaultNextCaption := WizardForm.NextButton.Caption;
  DefaultNextLeft := WizardForm.NextButton.Left;
  DefaultNextWidth := WizardForm.NextButton.Width;
  BuildWelcomePage();
  BuildMigratePage();
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  { Hide the stock Welcome page so our custom WelcomePage takes its place as
    the wizard's first screen (mock 1.2.1). }
  if PageID = wpWelcome then
    Result := True;
  { Keep the page hidden while allowing an explicit /GROUP for isolation.
    DisableProgramGroupPage=yes would ignore that command-line argument. }
  if PageID = wpSelectProgramGroup then
    Result := True;
  if (PageID = MigratePage.ID) and ((not LegacyYoinkPresent()) or IsolatedInstall()) then
    Result := True;
  { Skipping wpPreparing does not disable Restart Manager: Inno never calls
    ShouldSkipPage for that page. Isolated mode requires the documented
    /NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS switches instead.
    RegisterExtraCloseApplicationsResources only adds resources. }
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
begin
  if IsolatedSetupRequested() then
  begin
    if not SetPreviousData(PreviousDataKey, 'Isolated', '1') then
      RaiseException('isolated-persistence-failed: could not persist Isolated');
    if not SetPreviousData(PreviousDataKey, 'Profile', IsolatedProfile()) then
      RaiseException('isolated-persistence-failed: could not persist Profile');
    if not SetPreviousData(PreviousDataKey, 'Port', IntToStr(IsolatedPort())) then
      RaiseException('isolated-persistence-failed: could not persist Port');
    if not SetPreviousData(PreviousDataKey, 'AppDir', ExpandConstant('{app}')) then
      RaiseException('isolated-persistence-failed: could not persist AppDir');
  end;
end;

procedure RegisterExtraCloseApplicationsResources;
begin
  if IsolatedInstall() then
    Exit;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpSelectDir then
    Result := IsolatedValidateTargetDir(WizardDirValue);
end;

function IsolatedOwnedStop(const AppDir: String): Boolean;
var
  PythonExe, Script: String;
  ResultCode: Integer;
  Executed: Boolean;
begin
  Result := False;
  PythonExe := AddBackslash(AppDir) + 'python\python.exe';
  Script := AddBackslash(AppDir) + 'uoink_install_isolation.py';
  if (not FileExists(PythonExe)) or (not FileExists(Script)) then
  begin
    Log('isolated uninstall: owned stop launch failed; python or isolation script missing');
    Exit;
  end;
  Executed := Exec(
    PythonExe,
    '"' + Script + '" --isolated-stop --isolated-from-install-dir "' + AppDir + '"',
    AppDir,
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode);
  if not Executed then
  begin
    Log('isolated uninstall: owned stop Exec failed');
    Exit;
  end;
  if ResultCode <> 0 then
  begin
    Log('isolated uninstall: owned stop exited ' + IntToStr(ResultCode));
    Exit;
  end;
  Result := True;
end;

function InitializeUninstall(): Boolean;
var
  AppDir, IsolatedFlag, PersistedProfile, PersistedPort, PersistedAppDir: String;
  MarkerExists: Boolean;
begin
  Result := False;
  AppDir := ExpandConstant('{app}');
  IsolatedFlag := GetPreviousData('Isolated', '');
  PersistedProfile := GetPreviousData('Profile', '');
  PersistedPort := GetPreviousData('Port', '');
  PersistedAppDir := GetPreviousData('AppDir', '');
  MarkerExists := IsolatedMarkerFileExists(AppDir);

  if (CompareText(Trim(IsolatedFlag), '1') <> 0) and (not MarkerExists) then
  begin
    Result := True;
    Exit;
  end;

  (* Isolated or ambiguous uninstall: never fall back to ordinary stop-server.bat.
     UninstallRun nonzero exit does not gate deletion, so owned stop runs here. *)
  if IsolatedExistingAncestorsHaveReparse(AppDir) or IsolatedPathLooksDeviceOrUnc(AppDir) then
  begin
    IsolatedUninstallAbort('isolated-path-reparse: isolated uninstall refuses a reparse, device or UNC app directory before stop or deletion');
    Exit;
  end;

  if CompareText(Trim(IsolatedFlag), '1') <> 0 then
  begin
    IsolatedUninstallAbort('isolated-install-ordinary-reuse: refusing to adopt an ordinary uninstall as isolated, and refusing ordinary stop against an isolated marker');
    Exit;
  end;

  if (PersistedProfile = '') or (PersistedPort = '') or (PersistedAppDir = '') then
  begin
    IsolatedUninstallAbort('isolated-install-marker-mismatch: persisted isolated uninstall evidence is incomplete');
    Exit;
  end;

  if not IsolatedSamePath(PersistedAppDir, AppDir) then
  begin
    IsolatedUninstallAbort('isolated-install-marker-mismatch: persisted app directory differs; refusing deletion');
    Exit;
  end;

  if not MarkerExists then
  begin
    IsolatedUninstallAbort('isolated-install-marker-missing: isolated-install.json disappeared; refusing deletion');
    Exit;
  end;

  if not IsolatedMarkerWellFormed(AppDir) then
  begin
    IsolatedUninstallAbort('isolated-install-marker-mismatch: isolated-install.json is damaged; refusing deletion');
    Exit;
  end;

  if not IsolatedMarkerExact(AppDir, PersistedProfile, StrToIntDef(PersistedPort, -1)) then
  begin
    IsolatedUninstallAbort('isolated-install-marker-mismatch: isolated-install.json does not match persisted profile and port');
    Exit;
  end;

  if not IsolatedOwnedStop(AppDir) then
  begin
    IsolatedUninstallAbort('isolated-stop-failed: owned isolated stop failed or returned nonzero; refusing deletion');
    Exit;
  end;

  Result := True;
end;

(* v2.2.0 must-fix: stop the old helper + clear the splash sentinel BEFORE
   files are copied. Two related bugs both rooted in stale state across an
   upgrade:

     Bug 1 -- prior pythonw.exe still holds 127.0.0.1:5179 when the new
     helper's [Run] entry fires, so the new helper exits silently into a
     bound port (hit on 2.1.0->2.1.1 and 2.1.1->2.2.0).

     Bug 2 -- the .first-run-done sentinel from the prior install lives at
     %LOCALAPPDATA%\Uoink\.first-run-done, suppressing the splash for
     upgraders.

   The heavy lifting is in upgrade_prep.ps1 (graceful POST /helper/quit
   with the stored token, fallback Stop-Process under Yoink/Uoink roots,
   wait-for-port-free, sentinel delete, full logging to
   %TEMP%\uoink-upgrade-prep.log). Pascal also calls DeleteFile() on the
   sentinel directly as belt-and-suspenders -- if PowerShell itself
   failed to launch (locked down policy, missing pwsh, etc.) the upgrader
   still gets their splash. The script is non-fatal on any failure -- the
   worst case is the previously-shipping behaviour, which is what we have
   today, so a prep failure should never abort the install.

   Note: this block + the ones below use Pascal's other comment delimiter
   instead of the house brace style because Inno's Pascal Script does NOT
   nest comments, and the bodies below need to reference literal Inno
   constants whose names embed brace characters. *)
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ScriptPath: string;
  SentinelPath: string;
  ResultCode: Integer;
  Executed: Boolean;
  AppDir: String;
begin
  Result := '';
  NeedsRestart := False;
  AppDir := ExpandConstant('{app}');
  (* Final chosen directory is valid here. InitializeSetup must not treat the
     default {app} as the target. Ordinary setup against an isolated target
     refuses before ordinary preparation. *)
  if not IsolatedValidateTargetDir(AppDir) then
  begin
    if IsolatedErrorText <> '' then
      Result := IsolatedErrorText
    else
      Result := 'isolated install refused: target directory failed validation';
    Exit;
  end;
  (* Isolated installs never probe 5179, never stop a helper by name/prefix,
     and never touch the ordinary %LOCALAPPDATA%\Uoink splash sentinel.
     Revalidate close switches, declared inputs and path ancestors here. *)
  if IsolatedInstall() then
  begin
    if not IsolatedCloseSwitchesValid() then
    begin
      if IsolatedErrorText <> '' then
        Result := IsolatedErrorText
      else
        Result := 'isolated-close-applications-required: isolated mode requires /NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS';
      Exit;
    end;
    if not IsolatedValidateDeclaredInputs() then
    begin
      if IsolatedErrorText <> '' then
        Result := IsolatedErrorText
      else
        Result := 'isolated install refused: declared inputs failed PrepareToInstall revalidation';
      Exit;
    end;
    Log('PrepareToInstall: isolated mode skips upgrade_prep.ps1 and ordinary sentinel delete');
    Exit;
  end;
  SentinelPath := ExpandConstant('{localappdata}\Uoink\.first-run-done');

  (* dontcopy file -- ExtractTemporaryFile pulls it into {tmp} the first
     time we call it. ScriptPath then resolves to that {tmp} location. *)
  try
    ExtractTemporaryFile('upgrade_prep.ps1');
  except
    (* ExtractTemporaryFile raised. Skip the PS script + fall through to
       the direct sentinel delete below. *)
    Log('PrepareToInstall: ExtractTemporaryFile(upgrade_prep.ps1) failed');
  end;

  ScriptPath := ExpandConstant('{tmp}\upgrade_prep.ps1');
  if FileExists(ScriptPath) then
  begin
    Executed := Exec(
      'powershell.exe',
      '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + ScriptPath + '"',
      ExpandConstant('{tmp}'),
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode);
    if Executed then
      Log('PrepareToInstall: upgrade_prep.ps1 exited with code ' + IntToStr(ResultCode))
    else
      Log('PrepareToInstall: powershell.exe Exec() failed; falling through');
  end else
    Log('PrepareToInstall: upgrade_prep.ps1 missing under tmp; falling through');

  (* Belt-and-suspenders: directly remove the splash sentinel so even if
     the PS script never ran (PowerShell missing, ExecutionPolicy locked
     by a domain policy, ExtractTemporaryFile raised), the upgrader still
     sees the splash on first launch. DeleteFile is a no-op if the file
     is absent (clean install). *)
  if FileExists(SentinelPath) then
  begin
    if DeleteFile(SentinelPath) then
      Log('PrepareToInstall: removed splash sentinel ' + SentinelPath)
    else
      Log('PrepareToInstall: DeleteFile(' + SentinelPath + ') returned false');
  end;
end;

procedure VerifyInstalledHelper();
var
  ResultCode: Integer;
  VerifyScript: String;
  VerifyParams: String;
  VerifyOk: Boolean;
begin
  Log('Post-install verification: checking bundled files without starting helper');
  VerifyScript := ExpandConstant('{app}\verify_install.ps1');
  VerifyParams :=
    '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
    VerifyScript + '" -ExpectedVersion "{#AppVersion}"';
  VerifyOk := Exec(
    'powershell.exe',
    VerifyParams,
    ExpandConstant('{app}'),
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode);

  if (not VerifyOk) or (ResultCode <> 0) then
  begin
    Log('Post-install verification warning: files-only check failed with exit code ' + IntToStr(ResultCode));
    SuppressibleMsgBox(
      'Uoink is installed, but setup could not verify every bundled file.' +
      Chr(13) + Chr(10) + Chr(13) + Chr(10) +
      'You can still start Uoink. Details are in your Temp folder as uoink-install-verify.log.',
      mbInformation,
      MB_OK,
      IDOK);
    Exit;
  end;

  Log('Post-install verification: bundled files verified for {#AppVersion}');
end;

function WriteIsolatedMarker(): Boolean;
var
  MarkerPath, Body, AppDir: String;
begin
  AppDir := ExpandConstant('{app}');
  if IsolatedExistingAncestorsHaveReparse(AppDir) or IsolatedPathLooksDeviceOrUnc(AppDir) or
     IsolatedExistingAncestorsHaveReparse(IsolatedMarkerPath(AppDir)) then
  begin
    Result := False;
    Log('Post-install: refused isolated-install.json write through a reparse, device or UNC path');
    Exit;
  end;
  MarkerPath := IsolatedMarkerPath(AppDir);
  Body :=
    '{' + #13#10 +
    '  "mode": "isolated",' + #13#10 +
    '  "profile": "' + JsonEscape(IsolatedProfile()) + '",' + #13#10 +
    '  "port": ' + IntToStr(IsolatedPort()) + ',' + #13#10 +
    '  "host": "127.0.0.1",' + #13#10 +
    '  "app_dir": "' + JsonEscape(AppDir) + '"' + #13#10 +
    '}' + #13#10;
  if not SaveStringToFile(MarkerPath, Utf8Encode(Body), False) then
  begin
    Result := False;
    Log('Post-install: failed to write isolated-install.json');
    Exit;
  end;
  Result := IsolatedMarkerWellFormed(AppDir) and
            IsolatedMarkerExact(AppDir, IsolatedProfile(), IsolatedPort());
  if Result then
    Log('Post-install: wrote and verified isolated-install.json')
  else
    Log('Post-install: isolated-install.json persistence verification failed');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if IsolatedInstall() then
    begin
      if not WriteIsolatedMarker() then
        RaiseException('isolated-install-marker-write-failed: could not write isolated-install.json');
    end;
    VerifyInstalledHelper();
  end;
end;

{ Finding 2.2 (creative review v2.2, AG): override Next/Back chrome on
  Welcome so the primary CTA reads as a landing-page call to action ("Let's
  go ->") and the Back button is hidden (there is no Back from the first
  page). Inno resets button state on page transitions, so the customization
  is scoped to wpWelcome's custom-page id only; subsequent pages keep
  Inno's stock chrome with no else branch needed.

  IN-04 hardening (button DPI/glyph safety):
    * Caption uses a plain ASCII "->" arrow, matching the marketing site's
      button voice ("Download ->", "Open release ->"). This drops the old
      Chr($2192) Unicode right-arrow, which relied on the default wizard
      font carrying U+2192 and on the source-encoding dance (build.ps1
      writes the .iss BOM-less, read as cp1252). ASCII "->" renders in every
      font at every code page with zero glyph or encoding risk.
    * The button auto-sizes to its caption via SizeNextButtonToCaption
      instead of a hand-computed ScaleX(112) magic width. Measuring the
      real caption in the real button font at the real DPI means the label
      can never be clipped at 125%/150% Windows display scaling, and the
      button never carries dead padding. It is anchored by its right edge so
      the layout matches Inno's stock Next placement. }
procedure SizeNextButtonToCaption(const Cap: String);
var
  Meas: TNewStaticText;
  W: Integer;
begin
  WizardForm.NextButton.Caption := Cap;
  { Measure the caption in the button's own font so the width is correct at
    whatever DPI the wizard is running under. TNewStaticText.AutoSize gives us
    the rendered run width without guessing. }
  Meas := TNewStaticText.Create(WizardForm);
  try
    Meas.Parent := WizardForm;
    Meas.Visible := False;
    Meas.AutoSize := True;
    Meas.Font.Name := WizardForm.NextButton.Font.Name;
    Meas.Font.Size := WizardForm.NextButton.Font.Size;
    Meas.Font.Style := WizardForm.NextButton.Font.Style;
    Meas.Caption := Cap;
    W := Meas.Width + ScaleX(28);   { room for the button's internal padding }
  finally
    Meas.Free;
  end;
  if W < DefaultNextWidth then
    W := DefaultNextWidth;          { never narrower than Inno's stock Next }
  WizardForm.NextButton.Width := W;
  { Keep the right edge where Inno's stock Next button sits. }
  WizardForm.NextButton.Left := (DefaultNextLeft + DefaultNextWidth) - W;
end;
function UpdateReadyMemo(
  Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo,
  MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  (* v2.2.1 fix, kept compiler-compatible for v3.0.0: ReadyLabel1 ends with
     "...dependencies in:" and [Messages] cannot expand {app}. The Ready page
     exposes this hook for runtime memo text, so put the chosen install path
     there instead of reaching into a compiler-specific WizardForm label. *)
  Result := ExpandConstant('{app}');
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = WelcomePage.ID then
  begin
    SizeNextButtonToCaption('Let''s go ->');
    WizardForm.BackButton.Visible := False;
  end else
  begin
    WizardForm.NextButton.Caption := DefaultNextCaption;
    WizardForm.NextButton.Width := DefaultNextWidth;
    WizardForm.NextButton.Left := DefaultNextLeft;
  end;
end;
