@echo off
echo Starting ANI backend...
start "ANI FastAPI" cmd /k ".venv\Scripts\activate && uvicorn backend.main:app --reload"
timeout /t 2 >nul
echo Starting ANI frontend...
start "ANI Frontend" cmd /k ".venv\Scripts\activate && python -m http.server 8080"
echo.
echo ANI frontend: http://localhost:8080
echo API docs:     http://127.0.0.1:8000/docs
