@echo off
cd /d "%~dp0"
cls
echo ============================================================
echo   Moksha 2026 - Automated Vercel Deployment Helper
echo ============================================================
echo.
echo Step 1: Logging in to Vercel...
echo (Your browser will open. Click 'Verify' or 'Authorize')
echo.
call npx.cmd vercel login
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Login failed or cancelled.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ============================================================
echo Step 2: Deploying directly to Production...
echo (All prompts are automatically answered with --yes)
echo ============================================================
echo.
call npx.cmd vercel --prod --yes

echo.
echo ============================================================
echo Deployment process finished! Check the URL above.
echo ============================================================
pause
