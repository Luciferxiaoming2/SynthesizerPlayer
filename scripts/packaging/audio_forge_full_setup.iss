#define MyAppName "Audio Forge"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Synthesizer Player"
#define MyAppExeName "audio-forge-ui.exe"

[Setup]
AppId={{7F1C4A89-0C15-46A7-98E7-920C6AE61C53}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Audio Forge
DefaultGroupName=Audio Forge
DisableProgramGroupPage=yes
OutputDir=..\..\release
OutputBaseFilename=AudioForge_Full_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Files]
Source: "..\..\release\AudioForgePortable_next\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Audio Forge"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Audio Forge"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: checkedonce

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 Audio Forge"; Flags: nowait postinstall skipifsilent
