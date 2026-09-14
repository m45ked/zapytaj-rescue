@echo off
chcp 65001 >nul
title Zapytaj Onet Rescue Worker

echo ============================================================
echo   ZAPYTAJ ONET RESCUE - WORKER
echo ============================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [BLAD] Nie znaleziono Pythona w systemie!
    echo Pobierz i zainstaluj Pythona ze strony: https://www.python.org/
    pause
    exit /b 1
)

if not exist ".env" (
    echo [INFO] Tworzenie pliku .env z szablonu .env.example...
    copy .env.example .env >nul
    echo.
    echo ============================================================
    echo WAŻNE: Skonfiguruj darmowe klucze Internet Archive!
    echo Wejdź na: https://archive.org/account/s3.php
    echo i uzupełnij IA_ACCESS_KEY i IA_SECRET_KEY w pliku .env.
    echo ============================================================
    echo.
)

echo [1/2] Sprawdzanie i instalacja bibliotek...
python -m pip install -q -r requirements.txt

echo.
echo [2/2] Startowanie workera...
python main.py worker

pause
