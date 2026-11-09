# Mail-Sortierer für Windows installieren oder aktualisieren.
# Aufruf in PowerShell:  irm https://raw.githubusercontent.com/felixwrk/mail-sortierer/main/install/windows.ps1 | iex
$ErrorActionPreference = 'Stop'
$repo = 'felixwrk/mail-sortierer'
Write-Host ''
Write-Host '=========================================='
Write-Host '  Mail-Sortierer wird installiert'
Write-Host '=========================================='
Write-Host ''
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$dir = Join-Path $env:LOCALAPPDATA 'MailSortierer'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$exe = Join-Path $dir 'MailSortierer.exe'
Write-Host '1/3  Alte Version wird beendet ...'
Get-Process MailSortierer, MailSortierer-Windows -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800
Write-Host '2/3  Neueste Version wird geladen ...'
$ProgressPreference = 'SilentlyContinue'
Invoke-WebRequest "https://github.com/$repo/releases/latest/download/MailSortierer-Windows.exe" -OutFile $exe -UseBasicParsing
Unblock-File $exe
Write-Host '3/3  Verknüpfungen werden angelegt ...'
$ws = New-Object -ComObject WScript.Shell
foreach ($folder in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) {
  $lnk = $ws.CreateShortcut((Join-Path $folder 'Mail-Sortierer.lnk'))
  $lnk.TargetPath = $exe
  $lnk.WorkingDirectory = $dir
  $lnk.IconLocation = "$exe,0"
  $lnk.Description = 'Mail-Sortierer'
  $lnk.Save()
}
Write-Host ''
Write-Host 'Fertig! Du findest den Mail-Sortierer im Startmenü und auf dem Desktop.'
Write-Host 'Updates kommen ab jetzt automatisch über die App.'
Start-Process $exe
