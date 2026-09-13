[Setup]
AppName=Synthetic signing refusal
AppVersion=0.0.0
DefaultDirName={tmp}\SyntheticSigningRefusal
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=synthetic-refusal
SignTool=uoinkrelease
SignedUninstaller=yes
SignedUninstallerDir=cache
SignToolRetryCount=0
[Files]
Source: "fixture.txt"; DestDir: "{app}"