Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
AppDir = FSO.GetParentFolderName(WScript.ScriptFullName)
PythonW = AppDir & "\.venv\Scripts\pythonw.exe"
MainPy = AppDir & "\main.py"
If FSO.FileExists(PythonW) Then
    WshShell.CurrentDirectory = AppDir
    WshShell.Run """" & PythonW & """ """ & MainPy & """", 0, False
Else
    WshShell.CurrentDirectory = AppDir
    WshShell.Run "cmd /c uv run python main.py", 0, False
End If
