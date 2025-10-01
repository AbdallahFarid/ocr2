@echo off
echo ========================================
echo   Head Office Cheque Review System
echo ========================================
echo.
echo Stopping all services...
echo.

docker-compose down

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Failed to stop services!
    pause
    exit /b 1
)

echo.
echo ========================================
echo   All Services Stopped
echo ========================================
echo.
echo The application has been shut down safely.
echo.
pause
