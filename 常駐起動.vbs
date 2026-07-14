' Start Asana reminder in the background (no window).
' Finds pythonw.exe automatically so it works even if PATH is not set.
Option Explicit
Dim sh, fso, scriptDir, pyScript, pyw, candidates, i, la

Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
pyScript = scriptDir & "\asana_reminder.py"

la = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%")

candidates = Array( _
  la & "\Python\bin\pythonw.exe", _
  la & "\Python\pythoncore-3.14-64\pythonw.exe", _
  la & "\Programs\Python\Python314\pythonw.exe", _
  la & "\Programs\Python\Python313\pythonw.exe", _
  la & "\Programs\Python\Python312\pythonw.exe", _
  la & "\Microsoft\WindowsApps\pythonw.exe" )

pyw = ""
For i = 0 To UBound(candidates)
  If fso.FileExists(candidates(i)) Then
    pyw = candidates(i)
    Exit For
  End If
Next

If pyw = "" Then pyw = "pythonw.exe"

' 0 = hidden window, False = do not wait
sh.Run """" & pyw & """ """ & pyScript & """", 0, False
