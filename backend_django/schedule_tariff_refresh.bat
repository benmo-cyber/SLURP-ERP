@echo off
REM Windows Task Scheduler script to refresh tariffs every Sunday at 2am
REM Schedule this in Windows Task Scheduler:
REM - Trigger: Weekly, Sunday, 2:00 AM
REM - Action: Start a program
REM - Program: This batch file

cd /d "C:\Users\benmo\OneDrive\Documents\WWI ERP\backend_django"
call venv\Scripts\activate.bat
python manage.py refresh_tariffs
deactivate
