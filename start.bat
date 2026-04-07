@echo off
cd /d "%~dp0"
set PATH=C:\Users\ksenechkka queen\AppData\Local\Python\pythoncore-3.14-64;%PATH%
python -m pip install -q fastapi uvicorn openai python-dotenv pydantic
echo.
echo ================================
echo Starting ELI5 AI Explainer...
echo Open http://localhost:8000
echo ================================
echo.
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
pause
