@echo off
setlocal
cd /d "%~dp0"
set "SCRIPTDIR=%~dp0"

echo ============================================================
echo  Register auto-start (runs at Windows logon)
echo  Windows login ji ni jidou de kidou suru you ni touroku shimasu
echo ============================================================
echo.

rem === Create a Startup shortcut that runs the .vbs at logon ===
powershell -NoProfile -ExecutionPolicy Bypass -Command "$dir=$env:SCRIPTDIR.TrimEnd('\'); $vbs=(Get-ChildItem -Path $dir -Filter *.vbs | Select-Object -First 1).FullName; if(-not $vbs){Write-Host 'ERROR: .vbs not found'; exit 1}; $lnk=Join-Path ([Environment]::GetFolderPath('Startup')) 'AsanaReminder.lnk'; $ws=New-Object -ComObject WScript.Shell; $s=$ws.CreateShortcut($lnk); $s.TargetPath='wscript.exe'; $s.Arguments=('\"'+$vbs+'\"'); $s.WorkingDirectory=$dir; $s.WindowStyle=7; $s.Description='Asana Reminder'; $s.Save(); if(Test-Path $lnk){Write-Host 'OK: registered'}else{Write-Host 'FAILED'}"

echo.
echo Kanryou shita nara "OK: registered" to hyouji saremasu.
echo Jikai no Windows login kara jidou de ugokimasu.
echo (Ima sugu ugokasu nara jouchuu-kidou no .vbs wo double click)
echo.
pause
