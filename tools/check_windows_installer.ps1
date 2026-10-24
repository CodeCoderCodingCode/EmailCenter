param([string]$Version = '1.0.1')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$proof = Join-Path $root 'docs\abnahme\B_Release\DllFix'
$app = Join-Path $proof 'App'
$project = Join-Path $proof 'StartupProject'
$setup = Join-Path $root "dist\release\EmailCenter-Setup-$Version-Windows-x64.exe"
$registry = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{A2EF7697-3D66-4914-B84C-12A3113026C3}_is1'
if (-not $app.StartsWith($root + '\') -or (Test-Path -LiteralPath $app)) { throw 'QA target must be new and inside this workspace.' }
if (Test-Path -LiteralPath $registry) { throw 'Existing user installation found; do not replace its registration during QA.' }
New-Item -ItemType Directory -Path $proof -Force | Out-Null
$report = [ordered]@{
  installer_sha256 = (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash
  real_gmail_requests = 0
  native_ui_acceptance = $false
  native_other_user_test = $false
}
$env:PYTHONPATH = "$root\src;$root\tools"
$env:TEMP = $root
$env:TMP = $root
$env:QT_QPA_PLATFORM = 'offscreen'
$env:EMAILCENTER_DEBUG_IMPORTS = '1'
$python = Join-Path $root '.venv\Scripts\python.exe'
$running = $null
try {
  $process = Start-Process -FilePath $setup -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/NOICONS','/TASKS=',('/DIR="{0}"' -f $app),('/LOG="{0}"' -f (Join-Path $proof 'Install.log'))) -WindowStyle Hidden -PassThru -Wait
  $report.install_exit_code = $process.ExitCode
  if ($process.ExitCode -ne 0) { throw "Install failed: $($process.ExitCode)" }
  $env:EMAILCENTER_QA_APP = $app
  & $python -c 'import os; from windows_release_layout import validate_bundle; validate_bundle(os.environ["EMAILCENTER_QA_APP"])'
  if ($LASTEXITCODE -ne 0) { throw 'Installed payload is incomplete.' }
  $report.python_dll_present = Test-Path -LiteralPath (Join-Path $app '_internal\python313.dll')
  $executable = Join-Path $app 'EmailCenter.exe'
  $report.installed_executable_matches = (Get-FileHash $executable).Hash -eq (Get-FileHash (Join-Path $root 'dist\runtime\EmailCenter\EmailCenter.exe')).Hash
  $report.guide_identical = (Get-FileHash (Join-Path $app '_internal\guide\EmailCenter_Guide.html')).Hash -eq (Get-FileHash (Join-Path $root 'guide\EmailCenter_Guide.html')).Hash
  $process = Start-Process -FilePath $executable -WorkingDirectory $root -ArgumentList @('--self-check', ('"{0}"' -f (Join-Path $proof 'Installed_Check.json'))) -RedirectStandardOutput (Join-Path $proof 'Check_stdout.log') -RedirectStandardError (Join-Path $proof 'Check_stderr.log') -WindowStyle Hidden -PassThru -Wait
  $report.compiled_check_exit_code = $process.ExitCode
  if ($process.ExitCode -ne 0) { throw 'Installed offline PDF check failed.' }
  $env:EMAILCENTER_QA_PROJECT = $project
  & $python -c 'import os; from emailcenter.project import create_project; create_project(os.environ["EMAILCENTER_QA_PROJECT"], name="DLL Start Test").close()'
  if ($LASTEXITCODE -ne 0) { throw 'Could not create isolated startup project.' }
  $running = Start-Process -FilePath $executable -WorkingDirectory $root -ArgumentList @('--project', ('"{0}"' -f $project)) -RedirectStandardOutput (Join-Path $proof 'Startup_stdout.log') -RedirectStandardError (Join-Path $proof 'Startup_stderr.log') -WindowStyle Hidden -PassThru
  Start-Sleep -Seconds 8
  $running.Refresh()
  $report.program_started = -not $running.HasExited
  if ($running.HasExited) { throw "GUI exited early: $($running.ExitCode)" }
  Stop-Process -Id $running.Id
  $running.WaitForExit()
  $running = $null
  $report.intermediate_executable_removed = -not (Test-Path -LiteralPath (Join-Path $root 'build\pyinstaller\EmailCenter\EmailCenter.exe'))
  $starterOutput = Join-Path $proof 'Starter_Check.json'
  & (Join-Path $root 'Start_EmailCenter.cmd') '--self-check' $starterOutput
  $deadline = (Get-Date).AddSeconds(60)
  while (-not (Test-Path -LiteralPath $starterOutput) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
  if (-not (Test-Path -LiteralPath $starterOutput)) { throw 'Root starter did not complete its offline check.' }
  $report.root_starter_checked = (Get-Content -Raw -LiteralPath $starterOutput | ConvertFrom-Json).success
  if (-not $report.root_starter_checked) { throw 'Root starter offline check failed.' }
} catch {
  $report.error = $_.Exception.Message
} finally {
  if ($null -ne $running -and -not $running.HasExited) { Stop-Process -Id $running.Id }
  $uninstaller = Join-Path $app 'unins000.exe'
  if (Test-Path -LiteralPath $uninstaller) {
    $process = Start-Process -FilePath $uninstaller -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',('/LOG="{0}"' -f (Join-Path $proof 'Uninstall.log'))) -WindowStyle Hidden -PassThru -Wait
    $report.uninstall_exit_code = $process.ExitCode
  }
  $report.program_removed = -not (Test-Path -LiteralPath (Join-Path $app 'EmailCenter.exe'))
  $report.registry_removed = -not (Test-Path -LiteralPath $registry)
  $report.external_project_preserved = Test-Path -LiteralPath $project
  $report | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $proof 'Installer_Result.json') -Encoding utf8
}
$report | ConvertTo-Json
if ($report.Contains('error')) { exit 1 }
foreach ($name in @('python_dll_present','installed_executable_matches','guide_identical','program_started','intermediate_executable_removed','root_starter_checked','program_removed','registry_removed','external_project_preserved')) {
  if (-not $report[$name]) { throw "QA failed: $name" }
}
