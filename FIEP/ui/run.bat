@echo off
chcp 65001 >nul
title FIEP UI Test

cd /d "%~dp0"

if not exist venv (
    echo Creating local virtual environment...
    python -m venv venv
)

call venv\Scripts\activate

echo Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements-ui.txt

echo Running test_ui.py...
python test_ui.py

pause
