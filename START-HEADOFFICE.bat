@echo off
echo ========================================
echo   Head Office Cheque Review System
echo ========================================
echo.
echo Starting services...
echo.

REM Check if Docker Desktop is running
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Docker Desktop is not running!
    echo.
    echo Please start Docker Desktop first, then run this script again.
    echo.
    pause
    exit /b 1
)

echo Docker Desktop is running...
echo.

REM Start all services
echo Starting backend, frontend, and database...
docker-compose up -d

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Failed to start services!
    echo Please check the error messages above.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Services Started Successfully!
echo ========================================
echo.
echo Backend API:   http://localhost:8000
echo Frontend:      http://localhost:3000
echo.
echo Opening browser in 5 seconds...
timeout /t 5 /nobreak >nul
start http://localhost:3000
echo.
echo The application is now running!
echo.
echo To stop the application, run: STOP-HEADOFFICE.bat
echo.
pause
