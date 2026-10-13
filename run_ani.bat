@echo off
setlocal
if not exist .venv\Scripts\activate.bat (
    echo ANI environment not found. Run setup_ani.bat first.
    exit /b 1
)
echo Starting ANI Service...
start "ANI Service" cmd /k "call .venv\Scripts\activate.bat && uvicorn backend.main:app --host 127.0.0.1 --port 8000"
timeout /t 2 >nul
echo Starting ANI Interface...
start "ANI Interface" cmd /k "call .venv\Scripts\activate.bat && python -m http.server 8080 --bind 127.0.0.1"
echo.
echo ANI Interface: http://localhost:8080
echo API documentation: http://127.0.0.1:8000/docs
endlocal
