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
#define AppVersion    "0.0.0"
#define AppPublisher  "ReplayRyan"
#define AppURL        "https://uoink.video"

[Setup]
; v2.1 rename: a NEW AppId is generated so the Uoink product installs as its
; own entry rather than upgrading the old Yoink AppId in place -- the first-run
; helper (migrate_install.py) migrates the user's data, and the old Yoink
; install is left for its 7-day grace cleanup. Keep this fixed from v2.1 on.
AppId={{1CCDA47D-2347-43D1-99F4-BD6E7C231288}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
VersionInfoVersion={#AppVersion}.0
DefaultDirName={localappdata}\Uoink
DefaultGroupName=Uoink
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\build
OutputBaseFilename=Uoink-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Branded wizard bitmaps (Variant A magnet-U), regenerated each build by
; ../generate_bitmaps.py into installer/assets/. Compile-time only (baked into
; Setup.exe, not installed to {app}). 24-bit BMP per Inno's requirement.
WizardImageFile=assets\wizard-large.bmp
WizardSmallImageFile=assets\wizard-small.bmp
SetupIconFile=uoink.ico
UninstallDisplayIcon={app}\uoink.ico
UninstallDisplayName={#AppName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force
ChangesEnvironment=no

[Messages]
; Net-new copy (WIZARD-COPY-AND-BITMAPS.md s1) to land the Uoink voice on the
; otherwise-stock Inno screens. ASCII-safe punctuation only (no em-dashes) so
; the strings render identically regardless of the .iss code page.
WelcomeLabel2=Uoink pulls complete YouTube context - transcripts, screenshots, and comments - straight into your clipboard for Claude or ChatGPT.%n%nThis installer places the private local helper onto your machine. No accounts, no cloud dependencies. Setup completes in under a minute.
SelectDirDesc=Choose where to place Uoink's local files
SelectDirLabel3=Uoink runs a lightweight program on your computer to process YouTube transcripts and screenshots locally, keeping your research private. Setup will install these tools into the folder below.
ReadyLabel1=Uoink is ready to set up on your machine. Click Install to place the local helper and dependencies in:
StatusExtractFiles=Placing local helper files and media dependencies...
FinishedHeadingLabel=Uoink is Ready
FinishedLabelNoIcons=Uoink has been successfully installed. Open YouTube in your browser, find the rust 'Uoink' button under the video player, and click it to pull content.%n%nTo configure API keys, customize screenshot intervals, or search your saved corpora, click the browser extension icon.
FinishedLabel=Uoink has been successfully installed. Open YouTube in your browser, find the rust 'Uoink' button under the video player, and click it to pull content.%n%nTo configure API keys, customize screenshot intervals, or search your saved corpora, click the browser extension icon.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; Python embeddable distribution (already includes pythonw.exe + python.exe
; + the stdlib zip). After staging, Lib\site-packages contains yt_dlp.
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
; Cross-platform path/OS helpers -- server.py and migrate_install.py import
; this at module top. Omitting it crashes the helper before it binds the port.
Source: "staging\_platform.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\migrate_install.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\channels.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\workspaces.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\claims.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\scripts.py"; DestDir: "{app}"; Flags: ignoreversion
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
Source: "staging\assets\dashboard\*"; DestDir: "{app}\assets\dashboard"; Flags: ignoreversion recursesubdirs createallsubdirs
; Tier 2 GUI assets: splash HTML (served at /splash, wrapped by uoink_splash.py)
; and the shared brand-tokens stylesheet both pages consume.
Source: "staging\assets\splash\*"; DestDir: "{app}\assets\splash"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "staging\assets\brand\*";  DestDir: "{app}\assets\brand";  Flags: ignoreversion recursesubdirs createallsubdirs
; v2.2.0: canonical rust-U mark loaded by the tray glyph (uoink_tray._image
; reads {app}\assets\logo-mark-color.png at start) so the tray icon and the
; installer .ico render the same artwork from the same source PNG.
Source: "staging\assets\logo-mark-color.png"; DestDir: "{app}\assets"; Flags: ignoreversion
; Library-index migrations -- index._run_migrations applies these at boot.
; Sprint 19.6 / Fix 1: pre-Sprint-19.6 installers omitted these, causing
; the helper to crash with "no such table: schema_version" on first launch.
Source: "staging\migrations\*"; DestDir: "{app}\migrations"; Flags: recursesubdirs ignoreversion createallsubdirs
Source: "staging\stop-server.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\stop-server.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\verify_install.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\uoink.ico"; DestDir: "{app}"; Flags: ignoreversion

; v2.2.0 upgrade-prep PowerShell. Flags: dontcopy keeps it out of {app} --
; ExtractTemporaryFile() drops it into {tmp} during PrepareToInstall, runs
; it once, and the wizard's normal {tmp} cleanup deletes it after.
Source: "upgrade_prep.ps1"; Flags: dontcopy

[Icons]
; The launcher entry is plain "Uoink" (not "Uoink Server") -- users don't
; think in servers, and this matches the README + finish-page wording.
Name: "{group}\Uoink"; \
  Filename: "{app}\python\pythonw.exe"; \
  Parameters: """{app}\server.py"""; \
  WorkingDir: "{app}"; \
  IconFilename: "{app}\uoink.ico"; \
  Comment: "Start Uoink"

Name: "{group}\Stop Uoink"; \
  Filename: "{app}\stop-server.bat"; \
  WorkingDir: "{app}"; \
  IconFilename: "{app}\uoink.ico"; \
  Comment: "Stop Uoink"

Name: "{group}\Open Uoink folder"; \
  Filename: "{app}"; \
  IconFilename: "{app}\uoink.ico"; \
  Comment: "Open the Uoink install folder"

Name: "{group}\Uninstall Uoink"; \
  Filename: "{uninstallexe}"

[Registry]
; Auto-start the helper on every Windows login. uninsdeletevalue removes the
; entry on uninstall so we don't leave dead Run keys behind. The first-run
; helper (migrate_install.py) drops any legacy "Yoink" Run value.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "Uoink"; \
  ValueData: """{app}\python\pythonw.exe"" ""{app}\server.py"""; \
  Flags: uninsdeletevalue

[Run]
; "Launch Uoink now" checkbox on the finish page (default checked).
Filename: "{app}\python\pythonw.exe"; \
  Parameters: """{app}\server.py"""; \
  WorkingDir: "{app}"; \
  Description: "Launch Uoink now"; \
  Flags: postinstall nowait skipifsilent

[UninstallRun]
; Stop a running server before file removal so unins doesn't fail on locked
; site-packages files. waituntilterminated gives the process time to exit.
Filename: "{app}\stop-server.bat"; \
  WorkingDir: "{app}"; \
  Flags: runhidden waituntilterminated; \
  RunOnceId: "StopUoink"

[UninstallDelete]
; Pip and the running Python create files we didn't ship (.pyc caches, the
; PID file, the live log). Sweep the whole install dir on uninstall.
Type: files; Name: "{app}\server.log"
Type: files; Name: "{app}\server.pid"
Type: filesandordirs; Name: "{app}\python\Lib\site-packages\__pycache__"
Type: filesandordirs; Name: "{app}\python\Lib\site-packages"
Type: filesandordirs; Name: "{app}\python\__pycache__"

[Code]
{ Tier 2 GUI wizard customization (DESIGN-MOCKS-tier-2.pdf, section 1.2). What's
  in scope for v2.2 within Inno's modern-wizard ceiling:
    * Branded WizardImageFile + WizardSmallImageFile (magnet-U Variant A)
    * AG-voiced [Messages] copy on the standard Welcome/Ready/Installing/Finished
    * A custom CreateCustomPage Welcome (the "Uoink that shit." hero from mock
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

var
  WelcomePage:  TWizardPage;
  MigratePage:  TWizardPage;
  MigrateText:  TNewStaticText;

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
  L.Left := 0;
  L.Top := Top;
  L.Width := P.SurfaceWidth;
  L.Height := Height;
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
    'Pull any YouTube video into your AI workspace.');
  { Finding 2.1 (creative review v2.2, AG): step tracker above the hero.
    Sits at the top of the surface (y=15, height=18) so it reads as a
    breadcrumb above the wordmark hero, matching mock 1.2.1's layout. }
  AddLabel(WelcomePage, 'STEP 1 OF 4',       15,  18,  9, [fsBold], C_RUST);
  { Hero (mock 1.2.1). Rust on the cream wizard ground passes AA for large
    text (>=18pt bold); body copy below stays on the default ink-on-cream the
    wizard uses -- never rust on ink, per the contrast rules. }
  AddLabel(WelcomePage, 'Uoink that shit.',  20,  56, 28, [fsBold], C_RUST);
  AddLabel(WelcomePage,
    'Uoink turns any YouTube video into a clean, AI-ready doc on your disk.',
                                              92,  36, 11, [], C_INK);
  AddLabel(WelcomePage,
    'This installs the local helper that does the work. ' +
    'No account, no cloud. Takes about a minute.',
                                              138, 44, 10, [], C_INK);
  AddLabel(WelcomePage,
    'MIT - open source - uoink.video',        210, 18,  9, [fsItalic], C_RUST);
end;

procedure BuildMigratePage();
begin
  MigratePage := CreateCustomPage(wpReady, 'Migrating Yoink Data',
    'Moving your saved videos, settings, and API key safely to Uoink');
  MigrateText := TNewStaticText.Create(MigratePage);
  MigrateText.Parent := MigratePage.Surface;
  MigrateText.AutoSize := False;
  MigrateText.Left := 0;
  MigrateText.Top := 0;
  MigrateText.Width := MigratePage.SurfaceWidth;
  MigrateText.Height := MigratePage.SurfaceHeight;
  MigrateText.WordWrap := True;
  MigrateText.Caption :=
    'A previous Yoink install was found on this PC.' + #13#10#13#10 +
    'The first time Uoink starts, it will automatically copy your saved videos, ' +
    'settings, and Anthropic API key from Yoink into Uoink. Nothing is moved or ' +
    'deleted until a fully verified copy exists -- your old files stay in place ' +
    'for 7 days as a safety net, then are removed automatically.' + #13#10#13#10 +
    'If anything cannot be copied automatically, no data is lost: your old files ' +
    'remain at %LOCALAPPDATA%\Yoink\, and you can re-enter your Anthropic API key ' +
    'from the Uoink Settings menu at any time.';
end;

procedure InitializeWizard();
begin
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
  if (PageID = MigratePage.ID) and (not LegacyYoinkPresent()) then
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
begin
  Result := '';
  NeedsRestart := False;
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
  LaunchOk: Boolean;
  VerifyOk: Boolean;
begin
  Log('Post-install verification: launching helper for /health check');
  LaunchOk := Exec(
    ExpandConstant('{app}\python\pythonw.exe'),
    '"' + ExpandConstant('{app}\server.py') + '"',
    ExpandConstant('{app}'),
    SW_HIDE,
    ewNoWait,
    ResultCode);
  if not LaunchOk then
    Log('Post-install verification: helper launch Exec() returned false');

  Sleep(1500);
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
    MsgBox(
      'Uoink installed, but the local helper did not report version {#AppVersion} on /health.' +
      Chr(13) + Chr(10) + Chr(13) + Chr(10) +
      'Setup log: %TEMP%\uoink-install-verify.log',
      mbError,
      MB_OK);
    RaiseException('Post-install /health verification failed with exit code ' + IntToStr(ResultCode));
  end;

  Log('Post-install verification: helper /health returned {#AppVersion}');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    VerifyInstalledHelper();
end;

{ Finding 2.2 (creative review v2.2, AG): override Next/Back chrome on
  Welcome so the primary CTA reads as a landing-page call to action ("Let's
  go ->") and the Back button is hidden (there is no Back from the first
  page). Inno resets button state on page transitions, so the customization
  is scoped to wpWelcome's custom-page id only; subsequent pages keep
  Inno's stock chrome with no else branch needed.

  Arrow note: the U+2192 right-arrow is built via Chr($2192) rather than
  embedded as a literal byte sequence because build.ps1 writes the
  generated .iss without a BOM, and Inno Setup 6 reads BOM-less sources
  as the system ANSI code page (cp1252 on en-US Windows). A literal `arrow`
  encoded as UTF-8 would land as three garbage glyphs. Chr() builds the
  string at runtime from a numeric code point and dodges the entire
  source-encoding question. }
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
    WizardForm.NextButton.Caption := 'Let''s go ' + Chr($2192);
    WizardForm.BackButton.Visible := False;
  end;
end;
