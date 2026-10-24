#define AppVersion "1.0.1"
#ifnexist "..\dist\runtime\EmailCenter\_internal\python313.dll"
  #error "Python runtime missing. Run tools/build_windows_release.py first."
#endif
[Setup]
AppId={{A2EF7697-3D66-4914-B84C-12A3113026C3}
AppName=EmailCenter
AppVersion={#AppVersion}
AppPublisher=EmailCenter
AppComments=Bewerbungen, Dokumente und E-Mail-Builder
DefaultDirName={localappdata}\Programs\EmailCenter
DefaultGroupName=EmailCenter
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist\release
OutputBaseFilename=EmailCenter-Setup-{#AppVersion}-Windows-x64
SetupIconFile=EmailCenter.ico
UninstallDisplayIcon={app}\EmailCenter.exe
WizardStyle=modern
WizardImageFile=wizard.bmp
WizardSmallImageFile=wizard-small.bmp
Compression=lzma2/fast
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMADictionarySize=32768
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no
LicenseFile=LICENSE.txt
InfoBeforeFile=Welcome.txt
InfoAfterFile=Finish.txt
Uninstallable=not IsTestInstall
CreateUninstallRegKey=not IsTestInstall

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startmenuicon"; Description: "Verknüpfung im Startmenü erstellen"; Flags: unchecked
Name: "desktopicon"; Description: "Verknüpfung auf dem Desktop erstellen"; Flags: unchecked

[Files]
Source: "..\dist\runtime\EmailCenter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\EmailCenter\EmailCenter"; Filename: "{app}\EmailCenter.exe"; WorkingDir: "{app}"; Tasks: startmenuicon; Check: not IsTestInstall
Name: "{userprograms}\EmailCenter\Hilfe und Anleitung"; Filename: "{app}\_internal\guide\EmailCenter_Guide.html"; Tasks: startmenuicon; Check: not IsTestInstall
Name: "{userdesktop}\EmailCenter"; Filename: "{app}\EmailCenter.exe"; WorkingDir: "{app}"; Tasks: desktopicon; Check: not IsTestInstall

[Run]
Filename: "{app}\EmailCenter.exe"; WorkingDir: "{app}"; Description: "EmailCenter starten"; Flags: nowait postinstall skipifsilent; Check: not IsTestInstall

[Code]
function IsTestInstall: Boolean;
begin
  Result := ExpandConstant('{param:EMAILCENTERQA|0}') = '1';
end;
