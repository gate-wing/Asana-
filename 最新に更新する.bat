@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo  Asana Reminder - UPDATE
echo  saishin wo tsuikou shite reminder wo saikidou shimasu
echo  (git pull -^> restart)
echo ============================================================
echo.

rem === Check git ===
where git >nul 2>&1
if errorlevel 1 (
  echo [ERROR] git ga mitsukarimasen.
  echo   BPR-bu / kanrisha ni gosoudan kudasai.
  echo.
  pause
  exit /b 1
)

rem === git pull ===
echo git pull jikkou-chuu...
echo.
git pull
if errorlevel 1 (
  echo.
  echo [ERROR] git pull ni shippai shimashita.
  echo   config.ini ijou no henkou wo shite iru ka,
  echo   kaisen / kenri no mondai kamo shiremasen.
  echo   BPR-bu / kanrisha ni gosoudan kudasai.
  echo.
  pause
  exit /b 1
)

rem === Restart reminder ===
echo.
echo reminder wo saikidou shimasu...
taskkill /IM pythonw.exe /F >nul 2>&1

set "STARTED="
for %%V in ("%~dp0*.vbs") do (
  if not defined STARTED (
    start "" wscript.exe "%%~fV"
    set "STARTED=1"
  )
)
if not defined STARTED (
  echo [ERROR] .vbs ga mitsukarimasen. joujou-kidou.vbs wo kakunin shite kudasai.
  echo.
  pause
  exit /b 1
)

echo.
echo Kanryou shimashita. Saishin no settei de ugoite imasu.
echo (kono mado wa tojite OK desu)
echo.
pause
