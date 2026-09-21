@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Folgezettel Renamer

if not exist "%~dp0folgezettel_renamer.py" goto :not_extracted

set "PYEXE="
set "PYARGS="

py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 goto :use_py

python -c "import sys" >nul 2>&1
if not errorlevel 1 goto :use_python

python3 -c "import sys" >nul 2>&1
if not errorlevel 1 goto :use_python3

goto :no_python

:use_py
set "PYEXE=py"
set "PYARGS=-3"
goto :python_found

:use_python
set "PYEXE=python"
set "PYARGS="
goto :python_found

:use_python3
set "PYEXE=python3"
set "PYARGS="
goto :python_found

:python_found
%PYEXE% %PYARGS% -c "import tkinter" >nul 2>startup_error.log
if errorlevel 1 goto :no_tkinter

%PYEXE% %PYARGS% -c "from PIL import Image, ImageTk" >nul 2>startup_error.log
if not errorlevel 1 goto :start_app

echo Preparing image support. This is needed only once.
%PYEXE% %PYARGS% -m pip --version >nul 2>&1
if errorlevel 1 %PYEXE% %PYARGS% -m ensurepip --upgrade
%PYEXE% %PYARGS% -m pip install --user Pillow
if errorlevel 1 goto :pillow_failed

:start_app
%PYEXE% %PYARGS% "%~dp0folgezettel_renamer.py" 2>>startup_error.log
set "APP_EXIT=%ERRORLEVEL%"
if "%APP_EXIT%"=="0" exit /b 0

echo.
echo The program stopped because of an error.
echo Error details were saved to:
echo %~dp0startup_error.log
echo.
if exist startup_error.log type startup_error.log
pause
exit /b %APP_EXIT%

:not_extracted
echo The ZIP file has not been fully extracted.
echo.
echo Right-click the ZIP file, choose "Extract All", then open the extracted folder and double-click START.bat.
echo.
pause
exit /b 1

:no_python
echo Python 3 was not found.
echo.
echo Install Python 3 from python.org and enable "Add Python to PATH" during installation.
echo Then double-click START.bat again.
echo.
pause
exit /b 1

:no_tkinter
echo Python was found, but tkinter is unavailable.
echo Reinstall Python from python.org with the optional Tcl/Tk component enabled.
echo.
if exist startup_error.log type startup_error.log
pause
exit /b 1

:pillow_failed
echo.
echo Pillow could not be installed.
echo Check the internet connection, then run START.bat again.
echo.
if exist startup_error.log type startup_error.log
pause
exit /b 1
