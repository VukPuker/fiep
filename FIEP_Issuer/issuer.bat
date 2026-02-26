@echo off
title FIEP Issuer Launcher

echo ----------------------------------------
echo   FIEP Issuer - Setup and Launch
echo ----------------------------------------
echo.

REM Check if venv exists
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

echo Activating virtual environment...
call venv\Scripts\activate

echo Installing dependencies...
pip install --upgrade pip
pip install pyqt5 psutil cryptography argon2-cffi

echo.
echo Starting FIEP Issuer...
echo.

python issuer.py

echo.
echo FIEP Issuer finished.
pause
