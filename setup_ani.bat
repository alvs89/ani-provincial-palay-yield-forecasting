@echo off
setlocal
if not exist .venv\Scripts\python.exe (
    echo Creating ANI environment...
    python -m venv .venv
    if errorlevel 1 exit /b 1
)
call .venv\Scripts\activate.bat
if errorlevel 1 exit /b 1
echo Installing ANI requirements...
python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
echo Verifying ANI installation...
python verify_installation.py
if errorlevel 1 exit /b 1
echo.
echo ANI setup complete. Run run_ani.bat to start the application.
echo Model retraining is an explicit action: python -m ml.train_model
endlocal
