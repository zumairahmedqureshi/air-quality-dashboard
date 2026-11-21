@echo off
rem run          start the dashboard
rem run fetch    fetch new data
rem run charts   redraw charts
rem run setup    create venv and install packages

cd /d "%~dp0"
set "PY=%~dp0venv\Scripts\python.exe"

if /i "%~1"=="setup" goto setup
if not exist "%PY%" (
    echo venv not found, run: run setup
    exit /b 1
)
if /i "%~1"=="fetch"  ( "%PY%" pipeline.py & exit /b )
if /i "%~1"=="charts" ( "%PY%" pipeline.py --eda-only & exit /b )
"%PY%" -m streamlit run app.py
exit /b

:setup
if not exist "%PY%" py -3 -m venv venv || python -m venv venv
"%PY%" -m pip install -r requirements.txt
