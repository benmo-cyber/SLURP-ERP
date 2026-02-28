@echo off
REM Flexport HTS integration was removed. Tariffs are entered manually.
REM This script is kept for reference. You can remove any Windows Task Scheduler
REM job that ran this. The refresh_tariffs command now only prints a message.
cd /d "%~dp0"
if exist venv\Scripts\activate.bat call venv\Scripts\activate.bat
python manage.py refresh_tariffs
if exist venv\Scripts\activate.bat call venv\Scripts\deactivate.bat
