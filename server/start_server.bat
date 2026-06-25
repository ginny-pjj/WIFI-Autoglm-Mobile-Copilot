@echo off
chcp 65001 > nul
set ROOT=%~dp0..
cd /d "%ROOT%\server"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
if exist "%ROOT%\.venv\Scripts\python.exe" (
  "%ROOT%\.venv\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000
) else (
  python -m uvicorn main:app --host 0.0.0.0 --port 8000
)
