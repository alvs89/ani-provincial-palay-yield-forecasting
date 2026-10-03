@echo off
python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
echo.
echo Patching current frontend...
python tools\patch_frontend.py
echo.
echo Reproducing ANI model training...
python -m ml.train_model
echo.
echo Setup complete. Run run_ani.bat
