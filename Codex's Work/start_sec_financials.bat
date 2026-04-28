@echo off
setlocal

echo ============================================
echo SEC 10-Q / 10-K Financial Extractor
echo ============================================

set /p TICKER=Enter ticker (e.g., AAPL): 
set /p START_YEAR=Enter start year (e.g., 2020): 
set /p END_YEAR=Enter end year (e.g., 2025): 

if "%TICKER%"=="" (
  echo Ticker is required.
  pause
  exit /b 1
)

python sec_filing_financials.py "%TICKER%" "%START_YEAR%" "%END_YEAR%"
if errorlevel 1 (
  echo.
  echo Python script returned an error.
)

pause
