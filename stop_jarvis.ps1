# Stops a running Jarvis (standalone or from VS Code) and its hidden launcher.
$procs = Get-CimInstance Win32_Process |
    Where-Object { $_.Name -in 'python.exe', 'pythonw.exe', 'cmd.exe' -and $_.CommandLine -match 'jarvis\.py' }
if (-not $procs) { Write-Host 'Jarvis is not running.'; exit 0 }
foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
Write-Host "Stopped Jarvis ($($procs.Count) process(es))."
