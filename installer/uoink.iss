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
;   stop-server.bat   Stops the server via the PID file written at startup.
;   uoink.ico         Used for shortcuts and the uninstaller.

#define AppName       "Uoink"
#define AppVersion    "2.1.0"
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
SetupIconFile=uoink.ico
UninstallDisplayIcon={app}\uoink.ico
UninstallDisplayName={#AppName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force
ChangesEnvironment=no

[Messages]
; Net-new copy to land the Uoink voice on the otherwise-stock Inno screens.
WelcomeLabel2=Uoink turns any YouTube video into a clean, AI-ready doc on your disk.%n%nThis installs the local helper that does the work. No account, no cloud. Takes about a minute.
ReadyLabel1=Ready to uoink. Click Install to drop everything in:
FinishedLabelNoIcons=Uoink is installed. Open YouTube, find the rust U under any video, and click it.
FinishedLabel=Uoink is installed. Open YouTube, find the rust U under any video, and click it.

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
Source: "staging\index.py"; DestDir: "{app}"; Flags: ignoreversion
; Cross-platform path/OS helpers -- server.py and migrate_install.py import
; this at module top. Omitting it crashes the helper before it binds the port.
Source: "staging\_platform.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\migrate_install.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\uoink_mcp.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\uoink_mcp_tools.py"; DestDir: "{app}"; Flags: ignoreversion
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
Source: "staging\skills\*"; DestDir: "{app}\skills"; Flags: recursesubdirs ignoreversion createallsubdirs
; Library-index migrations -- index._run_migrations applies these at boot.
; Sprint 19.6 / Fix 1: pre-Sprint-19.6 installers omitted these, causing
; the helper to crash with "no such table: schema_version" on first launch.
Source: "staging\migrations\*"; DestDir: "{app}\migrations"; Flags: recursesubdirs ignoreversion createallsubdirs
Source: "staging\stop-server.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\stop-server.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\uoink.ico"; DestDir: "{app}"; Flags: ignoreversion

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
