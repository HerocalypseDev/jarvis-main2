# One-time setup for running Jarvis without VS Code.
#   powershell -ExecutionPolicy Bypass -File install_shortcuts.ps1            # Desktop shortcuts
#   powershell -ExecutionPolicy Bypass -File install_shortcuts.ps1 -Autostart # + start at login
#   powershell -ExecutionPolicy Bypass -File install_shortcuts.ps1 -RemoveAutostart
param([switch]$Autostart, [switch]$RemoveAutostart)
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$startup = Join-Path ([Environment]::GetFolderPath('Startup')) 'Jarvis.lnk'

if ($RemoveAutostart) {
    Remove-Item $startup -ErrorAction SilentlyContinue
    Write-Host 'Autostart removed.'; exit 0
}

# Pin the exact interpreter that has Jarvis's packages (PATH may hit the Store stub first).
$py = (& python -c 'import sys; print(sys.executable)').Trim()
if (-not (Test-Path $py)) { Write-Error 'Could not find python.'; exit 1 }
Set-Content -Path (Join-Path $dir 'jarvis_python.txt') -Value $py -Encoding ascii

$shell = New-Object -ComObject WScript.Shell
function New-Link($path, $target, $arguments, $desc) {
    $l = $shell.CreateShortcut($path)
    $l.TargetPath = $target; $l.Arguments = $arguments; $l.WorkingDirectory = $dir
    $l.Description = $desc; $l.IconLocation = "$env:SystemRoot\System32\SHELL32.dll,168"
    $l.Save()
}
$desktop = [Environment]::GetFolderPath('Desktop')
New-Link (Join-Path $desktop 'Jarvis.lnk') "$env:SystemRoot\System32\wscript.exe" "`"$dir\Jarvis.vbs`"" 'Start Jarvis'
New-Link (Join-Path $desktop 'Stop Jarvis.lnk') "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" `
    "-NoProfile -ExecutionPolicy Bypass -File `"$dir\stop_jarvis.ps1`"" 'Stop Jarvis'
Write-Host "Using python: $py"
Write-Host 'Desktop shortcuts created: Jarvis, Stop Jarvis.'
if ($Autostart) {
    New-Link $startup "$env:SystemRoot\System32\wscript.exe" "`"$dir\Jarvis.vbs`"" 'Start Jarvis at login'
    Write-Host 'Autostart enabled (Jarvis starts when you sign in).'
}
