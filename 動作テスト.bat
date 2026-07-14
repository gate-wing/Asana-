@echo off
setlocal
cd /d "%~dp0"

rem === Find python.exe (works even if PATH is not set) ===
set "PY="
if exist "%LOCALAPPDATA%\Python\bin\python.exe" set "PY=%LOCALAPPDATA%\Python\bin\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" set "PY=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not defined PY set "PY=python.exe"

echo ============================================================
echo  Asana Reminder - TEST RUN (shows log)
echo  Close this window when done. Normal use: joujou_kidou.vbs
echo ============================================================
echo Using Python: %PY%
echo.
"%PY%" "%~dp0asana_reminder.py"
echo.
echo (program ended)
pause
