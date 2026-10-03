@echo off
python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
echo.
echo Patching current frontend...
findstr /b /c:"const API_BASE=" app.js >nul
if not errorlevel 1 (
    echo Frontend already uses the ANI API; skipping the one-time patch.
) else (
    python tools\patch_frontend.py
    if errorlevel 1 exit /b 1
)
echo.
echo Reproducing ANI model training...
python -m ml.train_model
if errorlevel 1 exit /b 1
echo.
echo Setup complete. Run run_ani.bat
