' Starts Jarvis with no console window and no VS Code. Double-click, or use the Desktop shortcut
' made by install_shortcuts.ps1. Output goes to jarvis_standalone.log next to this file.
' Stop it with Stop Jarvis (stop_jarvis.ps1). Only one instance can run (single-instance lock).
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
py = "python"
pyFile = dir & "\jarvis_python.txt"   ' written by install_shortcuts.ps1: the exact python.exe to use
If fso.FileExists(pyFile) Then
    Set f = fso.OpenTextFile(pyFile, 1)
    line = Trim(f.ReadLine)
    f.Close
    If Len(line) > 0 Then py = line
End If
logPath = dir & "\jarvis_standalone.log"
If fso.FileExists(logPath) Then
    If fso.GetFile(logPath).Size > 5242880 Then   ' keep the log from growing forever, but keep one old copy
        oldPath = dir & "\jarvis_standalone.old.log"
        On Error Resume Next   ' log in use (Jarvis already running): skip rotating, no error popup
        If fso.FileExists(oldPath) Then fso.DeleteFile oldPath
        fso.MoveFile logPath, oldPath
        On Error GoTo 0
    End If
End If
cmd = "cmd /c cd /d """ & dir & """ && """ & py & """ -u jarvis.py >> """ & logPath & """ 2>&1"
sh.Run cmd, 0, False   ' 0 = hidden window, False = don't wait
