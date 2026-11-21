@echo off
cd /d "%~dp0"
cls
echo ============================================================
echo   Moksha 2026 - Automated Vercel Deployment Helper
echo ============================================================
echo.
echo [1/2] Verifying Vercel Authentication...
call npx.cmd vercel whoami >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Logged out. Opening browser to log in to Vercel...
    call npx.cmd vercel login
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Login failed or cancelled.
        pause
        exit /b %ERRORLEVEL%
    )
) else (
    echo Authenticated successfully!
)

echo.
echo ============================================================
echo [2/2] Deploying directly to Production on Vercel...
echo ============================================================
echo.
call npx.cmd vercel --prod --yes

echo.
echo ============================================================
echo Deployment Complete!
echo Both the Main Website and Admin Portal are live at the URL above.
echo.
echo Admin Portal: append /admin to your URL (Password: moksha2026)
echo ============================================================
pause
