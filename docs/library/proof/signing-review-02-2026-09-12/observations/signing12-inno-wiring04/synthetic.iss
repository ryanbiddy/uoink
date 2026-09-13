[Setup]
AppName=Synthetic signing refusal
AppVersion=0.0.0
DefaultDirName={tmp}\SyntheticSigningRefusal
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=synthetic-refusal
SignTool=uoinkrelease
SignedUninstaller=yes
SignedUninstallerDir=cache with spaces
SignToolRetryCount=0
[Files]
Source: "fixture.txt"; DestDir: "{app}"