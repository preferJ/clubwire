@echo off
cd /d "%~dp0"
if not exist ".env.example" (
  echo Copy CREATE_ENV.cmd and CREATE_ENV.py into your clubwire project folder first.
  pause
  exit /b 1
)
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" CREATE_ENV.py
) else (
  python CREATE_ENV.py
)
pause
