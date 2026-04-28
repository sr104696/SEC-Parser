@echo off
REM SEC Financial Data Toolkit - Startup Script
REM This script runs the SEC financial data extractor

echo ============================================================
echo SEC Financial Data Toolkit
echo ============================================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Checking required packages...
python -c "import requests" >nul 2>&1
if errorlevel 1 (
    echo Installing requests...
    pip install requests
)

python -c "from bs4 import BeautifulSoup" >nul 2>&1
if errorlevel 1 (
    echo Installing beautifulsoup4...
    pip install beautifulsoup4 lxml
)

echo.
echo Starting SEC Financial Data Toolkit...
echo.

REM Run the Python script
python "%~dp0sec_unified.py"

echo.
pause
