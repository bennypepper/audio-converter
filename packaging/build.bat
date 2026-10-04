@echo off
setlocal
cd /d "%~dp0\.."
if not exist .venv-build ( python -m venv .venv-build || goto :fail )
call .venv-build\Scripts\activate.bat || goto :fail
python -m pip install --upgrade pip >nul
python -m pip install -r requirements-build.txt || goto :fail
python packaging\build.py %* || goto :fail
echo.
echo Done. The zip is in the dist folder.
exit /b 0
:fail
echo.
echo [ERROR] Build failed - see the messages above.
exit /b 1
