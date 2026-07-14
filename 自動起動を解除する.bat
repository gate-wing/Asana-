@echo off
setlocal
set "LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\AsanaReminder.lnk"
if exist "%LNK%" (
  del "%LNK%"
  echo Kaijo shimashita: auto-start wo mukou ni shimashita.
) else (
  echo Auto-start wa touroku sarete imasen.
)
echo.
echo Ima ugoiteiru reminder wo tomeru niwa:
echo   Task Manager de "pythonw.exe" wo shuuryou shite kudasai.
echo.
pause
