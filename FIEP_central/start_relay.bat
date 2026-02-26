@echo off
title FIEP Central Relay

echo ================================================
echo   FIEP CENTRAL RELAY — STARTUP SCRIPT
echo ================================================
echo.

REM --- Проверка Python ---
python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo [ERROR] Python не найден. Установи Python 3.10+ и добавь в PATH.
    pause
    exit /b
)

REM --- Создание виртуального окружения ---
if not exist venv (
    echo Создаю виртуальное окружение...
    python -m venv venv
)

REM --- Активация окружения ---
echo Активирую виртуальное окружение...
call venv\Scripts\activate

REM --- Установка зависимостей ---
echo Устанавливаю зависимости...
pip install --upgrade pip
pip install aiohttp

REM --- Запуск relay ---
echo.
echo ================================================
echo   Запуск центрального релея...
echo ================================================
echo.

python run.py

echo.
echo Relay завершил работу.
pause
