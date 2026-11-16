@echo off
rem ------------------------------------------------------------------------------------------
rem  PawConnect - one-click start for Windows.
rem    start.bat          create/prepare everything that is missing, then start the website
rem    start.bat seed     the same, and also add sample accounts and demo data first
rem  Every step stops with a clear message when something goes wrong - nothing is hidden.
rem ------------------------------------------------------------------------------------------
setlocal
cd /d "%~dp0"
title PawConnect
echo.
echo ==============================================
echo   PawConnect - starting
echo ==============================================

rem ---- 1. Python -----------------------------------------------------------------------------
set "PY=python"
python --version >nul 2>nul
if errorlevel 1 set "PY=py -3"
%PY% --version >nul 2>nul
if errorlevel 1 goto :no_python
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 goto :old_python

rem ---- 2. Virtual environment ----------------------------------------------------------------
if exist ".venv\Scripts\activate.bat" goto :activate
echo Creating the virtual environment .venv - first run only ...
%PY% -m venv .venv
if errorlevel 1 goto :venv_failed

:activate
call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :venv_failed

rem ---- 3. Settings file ------------------------------------------------------------------------
if exist ".env" goto :packages
copy ".env.example" ".env" >nul
if errorlevel 1 goto :env_failed
echo.
echo [ACTION NEEDED] A settings file named .env was created for you.
echo   1. Open .env in VS Code.
echo   2. Type your MySQL password after DB_PASSWORD= and save the file.
echo   3. Make sure MySQL is running, then double-click start.bat again.
goto :stop

rem ---- 4. Python packages ----------------------------------------------------------------------
:packages
python -c "import flask, flask_sqlalchemy, flask_login, flask_wtf, pymysql, dotenv" >nul 2>nul
if not errorlevel 1 goto :database
echo Installing the required Python packages - needs an internet connection, first run only ...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto :pip_failed

rem ---- 5. Database -------------------------------------------------------------------------------
:database
echo.
echo Preparing the database ...
if /i "%~1"=="seed" goto :seed
python init_db.py
if errorlevel 1 goto :db_failed
goto :run

:seed
python init_db.py --seed
if errorlevel 1 goto :db_failed

rem ---- 6. Start the website ----------------------------------------------------------------------
:run
echo.
echo Starting PawConnect - open http://127.0.0.1:5000/ in your browser. Press Ctrl+C to stop.
python run.py
if errorlevel 1 goto :run_failed
goto :stop

rem ---- Problems ------------------------------------------------------------------------------------
:no_python
echo.
echo [ERROR] Python was not found.
echo   Install Python 3.10 or newer from https://www.python.org/downloads/
echo   and tick "Add python.exe to PATH" in the installer, then run start.bat again.
goto :fail

:old_python
echo.
echo [ERROR] This Python is too old. PawConnect needs Python 3.10 or newer.
echo   Install a newer version from https://www.python.org/downloads/ and run start.bat again.
goto :fail

:venv_failed
echo.
echo [ERROR] The virtual environment could not be created or activated.
echo   Delete the .venv folder if it exists, then run start.bat again.
goto :fail

:env_failed
echo.
echo [ERROR] The settings file .env could not be created. Copy .env.example to .env yourself.
goto :fail

:pip_failed
echo.
echo [ERROR] The Python packages could not be installed. Check your internet connection and read the messages above.
goto :fail

:db_failed
echo.
echo [ERROR] The database could not be prepared. Read the message above: it explains what to fix.
echo   Most often MySQL is not running or the DB_USER / DB_PASSWORD values in .env are wrong.
goto :fail

:run_failed
echo.
echo [ERROR] PawConnect stopped with an error. Read the messages above.
goto :fail

:fail
echo.
pause
endlocal
exit /b 1

:stop
echo.
pause
endlocal
exit /b 0
