@echo off
setlocal EnableExtensions
title LiveFloat Launcher
cd /d "%~dp0"

set "VENV=.venv\Scripts\python.exe"
set "PYEXE="

rem ---------------------------------------------------------------
rem Find a working Python 3.10 - 3.12 (needed only for source mode).
rem The prebuilt dist\LiveFloat\LiveFloat.exe does NOT need Python.
rem ---------------------------------------------------------------
call :trypy "py -3.12"
if not defined PYEXE call :trypy "py -3.11"
if not defined PYEXE call :trypy "py -3.10"
if not defined PYEXE call :trypy "py"
if not defined PYEXE call :trypy "python"

if not defined PYEXE goto :nopython
if exist "%VENV%" goto :run

echo.
echo [LiveFloat] First run: creating virtual environment and installing
echo            dependencies (needs internet, takes a few minutes)...
echo.
"%PYEXE%" -m venv .venv
if not exist "%VENV%" goto :venvfail

"%VENV%" -m pip install --upgrade pip -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
"%VENV%" -m pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
if errorlevel 1 goto :depsfail

:run
echo [LiveFloat] Starting...
"%VENV%" run.py
echo.
echo [LiveFloat] Program exited (code %ERRORLEVEL%).
goto :end

:nopython
echo.
echo [ERROR] No Python 3.10 - 3.12 was found.
echo.
echo You have two options:
echo   1. Simply run the ready-to-use program:
echo        dist\LiveFloat\LiveFloat.exe     (no Python needed)
echo   2. Install Python 3.12 from https://www.python.org/downloads/
echo      and tick "Add python.exe to PATH", then run this file again.
goto :end

:venvfail
echo [ERROR] Failed to create the virtual environment.
goto :end

:depsfail
echo [ERROR] Dependency installation failed. Check your network and retry.
goto :end

:end
echo.
pause
exit /b 0

rem ---------------------------------------------------------------
rem Resolve a Python command to its real executable path, only if the
rem version is in the 3.10..3.12 range we support.
rem ---------------------------------------------------------------
:trypy
set "PYEXE="
for /f "usebackq delims=" %%P in (`%~1 -c "import sys;print(sys.executable) if (3,10)<=sys.version_info[:2]<(3,13) else print('')" 2^>nul`) do (
    if not "%%P"=="" set "PYEXE=%%P"
)
exit /b 0
