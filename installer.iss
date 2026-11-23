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
Name: "browserintegration"; Description: "Allow the Z browser extension to send links for review"; GroupDescription: "Browser integration:"; Flags: unchecked
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "dist\NexusDownloadManager\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "browser-extension\native-host.json"; DestDir: "{app}"; Flags: ignoreversion; Tasks: browserintegration
Source: "browser-extension\*"; DestDir: "{app}\browser-extension"; Flags: ignoreversion recursesubdirs createallsubdirs; Tasks: browserintegration

[Registry]
Root: HKCU; Subkey: "Software\Google\Chrome\NativeMessagingHosts\com.zyvelia.z_download_manager"; ValueType: string; ValueName: ""; ValueData: "{app}\native-host.json"; Flags: uninsdeletekey; Tasks: browserintegration
Root: HKCU; Subkey: "Software\Opera Software\NativeMessagingHosts\com.zyvelia.z_download_manager"; ValueType: string; ValueName: ""; ValueData: "{app}\native-host.json"; Flags: uninsdeletekey; Tasks: browserintegration

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
