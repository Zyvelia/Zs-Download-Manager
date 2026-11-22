#define MyAppName "Z's Download Manager"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Zyvelia"
#define MyAppExeName "NexusDownloadManager.exe"

[Setup]
AppId={{7B202A23-4B83-4D73-96B2-5ED14D2B5A7F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\NexusDownloadManager
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
OutputDir=installer-output
OutputBaseFilename=NexusDownloadManager-Setup
SetupIconFile=assets\logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "dist\NexusDownloadManager\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
