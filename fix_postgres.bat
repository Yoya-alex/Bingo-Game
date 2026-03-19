@echo off
echo ============================================================
echo PostgreSQL Password Reset - Automated Script
echo ============================================================
echo.
echo This script will:
echo 1. Backup pg_hba.conf
echo 2. Temporarily disable password authentication
echo 3. Reset passwords
echo 4. Restore security settings
echo.
echo IMPORTANT: This script must be run as Administrator!
echo.
pause

REM Check for admin rights
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script must be run as Administrator!
    echo Right-click this file and select "Run as administrator"
    pause
    exit /b 1
)

echo.
echo [1/6] Backing up pg_hba.conf...
copy "C:\Program Files\PostgreSQL\18\data\pg_hba.conf" "C:\Program Files\PostgreSQL\18\data\pg_hba.conf.backup" >nul 2>&1
if %errorLevel% equ 0 (
    echo [OK] Backup created
) else (
    echo [ERROR] Could not create backup. Check if PostgreSQL 18 is installed.
    pause
    exit /b 1
)

echo.
echo [2/6] Modifying pg_hba.conf to trust mode...
powershell -Command "(Get-Content 'C:\Program Files\PostgreSQL\18\data\pg_hba.conf') -replace 'scram-sha-256', 'trust' -replace 'md5', 'trust' | Set-Content 'C:\Program Files\PostgreSQL\18\data\pg_hba.conf'"
echo [OK] Modified

echo.
echo [3/6] Restarting PostgreSQL service...
net stop postgresql-x64-18 >nul 2>&1
timeout /t 2 /nobreak >nul
net start postgresql-x64-18 >nul 2>&1
timeout /t 3 /nobreak >nul
echo [OK] Service restarted

echo.
echo [4/6] Resetting passwords and creating database...
python reset_postgres_password.py
if %errorLevel% neq 0 (
    echo [ERROR] Password reset failed
    goto restore
)

:restore
echo.
echo [5/6] Restoring pg_hba.conf security settings...
copy "C:\Program Files\PostgreSQL\18\data\pg_hba.conf.backup" "C:\Program Files\PostgreSQL\18\data\pg_hba.conf" >nul 2>&1
echo [OK] Restored

echo.
echo [6/6] Restarting PostgreSQL service...
net stop postgresql-x64-18 >nul 2>&1
timeout /t 2 /nobreak >nul
net start postgresql-x64-18 >nul 2>&1
timeout /t 3 /nobreak >nul
echo [OK] Service restarted

echo.
echo ============================================================
echo PostgreSQL Password Reset Complete!
echo ============================================================
echo.
echo Credentials:
echo   Database: bingo_bot
echo   User: yoadmin
echo   Password: aaeyb
echo.
echo Next step: Run migrations
echo   python manage.py migrate
echo.
pause
