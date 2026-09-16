; Floating Bar Windows installer
; Builds from the PyInstaller artifact: dist\FloatingBar.exe

#define MyAppName "Floating Bar"
#define MyAppExeName "FloatingBar.exe"
#define MyAppPublisher "Floating Bar"
#define MyAppUrl "https://github.com/pyraxxz/Floating-Bar"

[Setup]
AppId={{9F35C7B7-5F3A-4AB1-8D24-8B2B1A6E4A51}
AppName={#MyAppName}
AppVersion={#GetEnv('FLOATINGBAR_VERSION')}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppUrl}
AppSupportURL={#MyAppUrl}
AppUpdatesURL={#MyAppUrl}/releases
DefaultDirName={autopf}\Floating Bar
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer-output
OutputBaseFilename=FloatingBar-Setup-{#GetEnv('FLOATINGBAR_VERSION')}
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "startup"; Description: "Start Floating Bar when I sign in to Windows"; GroupDescription: "Startup:"

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\FloatingBar"
