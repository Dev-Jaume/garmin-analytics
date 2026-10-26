param([switch]$NoShortcut, [switch]$NoLaunch)
$ErrorActionPreference = 'Stop'
$SourceRoot = Split-Path $PSScriptRoot -Parent
$ProgramRoot = Join-Path $env:LOCALAPPDATA 'Programs\GarminRunningAnalytics'
$DataRoot = Join-Path $env:LOCALAPPDATA 'GarminRunningAnalytics'
$Python = $null
try {
    $Candidate = & py -3.12 -c 'import sys; print(sys.executable)' 2>$null
    if ($LASTEXITCODE -eq 0) { $Python = $Candidate.Trim() }
} catch { }
if (-not $Python) {
    try {
        $Command = Get-Command python -ErrorAction Stop
        if ($Command.Source -notlike '*WindowsApps*') {
            $Candidate = & $Command.Source -c 'import sys; assert sys.version_info[:2] == (3,12); print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0) { $Python = $Candidate.Trim() }
        }
    } catch { }
}
if (-not $Python) {
    $Candidate = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    if (Test-Path $Candidate) { $Python = $Candidate }
}
if (-not $Python) {
    Write-Host 'Cal Python 3.12 de 64 bits. Intentant instal·lació per a aquest usuari...'
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'Instal·la Python 3.12 de python.org i torna a obrir Instal·lar.cmd.'
    }
    & winget install --exact --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw 'No s’ha pogut instal·lar Python. Visita python.org.' }
    $Python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    if (-not (Test-Path $Python)) { throw 'Reobre Instal·lar.cmd després d’instal·lar Python.' }
}
& $Python -c 'import sys; assert sys.version_info[:2] == (3,12) and sys.maxsize > 2**32'
if ($LASTEXITCODE -ne 0) { throw 'Cal Python 3.12 de 64 bits.' }
New-Item -ItemType Directory -Force $ProgramRoot | Out-Null
New-Item -ItemType Directory -Force $DataRoot | Out-Null
# Un entorn nou per actualització. No es toca la versió anterior ni cap dada personal.
$Version = '0.2.0'
$InstallId = [Guid]::NewGuid().ToString('N')
$Venv = Join-Path $ProgramRoot "versions\$Version-$InstallId"
& $Python -m venv $Venv
if ($LASTEXITCODE -ne 0) { throw 'No s’ha pogut crear l’entorn Python.' }
$AppPython = Join-Path $Venv 'Scripts\python.exe'
& $AppPython -m pip install --disable-pip-version-check -r (Join-Path $SourceRoot 'requirements-desktop.lock')
if ($LASTEXITCODE -ne 0) { throw 'No s’han instal·lat les dependències. La versió anterior es conserva.' }
& $AppPython -m pip install --no-deps $SourceRoot
if ($LASTEXITCODE -ne 0) { throw 'No s’ha instal·lat l’aplicació. La versió anterior es conserva.' }
& $AppPython -m garmin_running.desktop.launcher --diagnose
if ($LASTEXITCODE -ne 0) { throw 'La comprovació local d’instal·lació ha fallat.' }
$Launcher = Join-Path $ProgramRoot 'Obrir.cmd'
$LaunchText = "@echo off`r`nchcp 65001 >nul`r`n`"$AppPython`" -m garmin_running.desktop.launcher`r`n"
[IO.File]::WriteAllText($Launcher, $LaunchText, [Text.UTF8Encoding]::new($false))
if (-not $NoShortcut) {
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Garmin Running Analytics.lnk'))
    $Shortcut.TargetPath = $AppPython
    $Shortcut.Arguments = '-m garmin_running.desktop.launcher'
    $Shortcut.WorkingDirectory = $ProgramRoot
    $Shortcut.WindowStyle = 7
    $Shortcut.Description = 'Historial Garmin local i privat'
    $Shortcut.Save()
}
Write-Host "Instal·lació correcta. Dades locals: $DataRoot"
Write-Host 'La clau només es configurarà dins l’aplicació. No es llegeix cap clau de Codex.'
if (-not $NoLaunch) { Start-Process -FilePath $Launcher }
