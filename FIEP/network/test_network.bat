@echo off
title FIEP Network Test Suite

cd /d "%~dp0"

if not exist venv (
    echo Creating local virtual environment...
    python -m venv venv
)

call venv\Scripts\activate

set PYTHONPATH=%~dp0\..\..

echo ============================================
echo   FIEP NETWORK TEST SUITE (LOCAL VENV)
echo ============================================
echo.

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo Running test_network.py ...
python -m FIEP.network.test_network
echo.

echo ============================================
echo   ALL TESTS COMPLETED
echo ============================================
pause

