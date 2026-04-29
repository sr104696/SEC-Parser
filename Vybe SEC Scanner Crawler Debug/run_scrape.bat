@echo off
setlocal EnableExtensions

REM ============================================================
REM SEC Scanner Vybe Crawler Debug Runner
REM Creates venv, installs deps, installs Chromium, runs crawl.
REM Default target: https://sec-scanner-abd-inc22.vybe.build/
REM Default ticker test: BE
REM ============================================================

set "PROJECT_DIR=%~dp0"
set "SCRIPT_PATH=%PROJECT_DIR%crawl_vybe_app.py"
set "VENV_DIR=%PROJECT_DIR%.venv"
set "OUTPUT_DIR=%PROJECT_DIR%output"
set "DEBUG_DIR=%PROJECT_DIR%debug"

set "DEFAULT_URL=https://sec-scanner-abd-inc22.vybe.build/"
set "DEFAULT_OUTPUT=%OUTPUT_DIR%\sec_scanner_vybe_full.md"
set "DEFAULT_TICKER=BE"

if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"
if not exist "%DEBUG_DIR%" mkdir "%DEBUG_DIR%"

if not exist "%SCRIPT_PATH%" (
    echo ERROR: Could not find crawl_vybe_app.py
    echo Expected:
    echo   %SCRIPT_PATH%
    pause
    exit /b 1
)

where py >nul 2>&1
if %errorlevel%==0 (
    set "PY_BOOTSTRAP=py -3"
) else (
    where python >nul 2>&1
    if %errorlevel%==0 (
        set "PY_BOOTSTRAP=python"
    ) else (
        echo ERROR: Python was not found.
        echo Install Python 3.10+ from https://www.python.org/downloads/
        pause
        exit /b 1
    )
)

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY_BOOTSTRAP% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
)

set "PY=%VENV_DIR%\Scripts\python.exe"

echo.
echo Upgrading pip...
"%PY%" -m pip install --upgrade pip
if errorlevel 1 (
    echo ERROR: Failed to upgrade pip.
    pause
    exit /b 1
)

echo.
echo Installing dependencies...
"%PY%" -m pip install -r "%PROJECT_DIR%requirements.txt"
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo Installing Playwright Chromium...
"%PY%" -m playwright install chromium
if errorlevel 1 (
    echo ERROR: Failed to install Playwright Chromium.
    pause
    exit /b 1
)

set "BASE_URL=%~1"
if "%BASE_URL%"=="" (
    set "BASE_URL=%DEFAULT_URL%"
) else (
    shift
)

REM Override with: set TICKER=AAPL && run_scrape.bat
if "%TICKER%"=="" set "TICKER=%DEFAULT_TICKER%"

echo.
echo ============================================================
echo Running SEC Scanner Vybe crawler
echo URL:
echo   %BASE_URL%
echo Ticker:
echo   %TICKER%
echo Output:
echo   %DEFAULT_OUTPUT%
echo Debug:
echo   %DEBUG_DIR%
echo Extra args:
echo   %*
echo ============================================================
echo.

"%PY%" "%SCRIPT_PATH%" "%BASE_URL%" ^
  --output "%DEFAULT_OUTPUT%" ^
  --debug-dir "%DEBUG_DIR%" ^
  --ticker "%TICKER%" ^
  --max-pages 50 ^
  --concurrency 4 ^
  --settle-ms 2500 ^
  --timeout-ms 30000 ^
  %*

if errorlevel 1 (
    echo.
    echo ERROR: Crawler failed.
    echo Try headed debug mode:
    echo   set TICKER=BE
    echo   run_scrape.bat %BASE_URL% --headed --settle-ms 5000 --concurrency 1
    pause
    exit /b 1
)

echo.
echo Done.
echo Markdown output:
echo   %DEFAULT_OUTPUT%
echo Diagnostics:
echo   %DEBUG_DIR%\diagnostics.json
echo.
pause
exit /b 0
