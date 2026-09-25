@echo off
title Building Argus Studio & Windows Installer
echo ==============================================
echo   Packaging Argus Studio with Official Icon
echo ==============================================
echo.
python -m PyInstaller --noconsole --onefile --name "ArgusStudio" --icon "%~dp0app_icon.ico" --add-data "%~dp0app_icon.ico;." --collect-all customtkinter --collect-all yt_dlp --collect-all mutagen "%~dp0app.py"
copy /Y "%~dp0dist\ArgusStudio.exe" "%~dp0dist\Argus Studio.exe" >nul
echo.
echo ==============================================
echo   Compiling Windows Setup Wizard (.exe)
echo ==============================================
echo.
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" (
    "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" "%~dp0installer.iss"
    echo.
    echo [SUCCESS] Installer ready at:
    echo %~dp0dist\ArgusStudio-Setup.exe
) else (
    echo [NOTE] Inno Setup compiler not found. Standalone EXE is ready in dist\
)
echo.
pause
