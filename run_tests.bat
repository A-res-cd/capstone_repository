@echo off
cd /d "%~dp0"
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" "scripts\test_gui.py"
) else (
    if exist ".venv\Scripts\python.exe" (
        ".venv\Scripts\python.exe" "scripts\test_gui.py"
    ) else (
        python "scripts\test_gui.py"
    )
)
if errorlevel 1 pause
