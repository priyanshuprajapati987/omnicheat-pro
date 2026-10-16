@echo off
cd /d D:\JARVES\omnicheat-pro\backend
call venv\Scripts\activate.bat
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --log-level debug
