@echo off
start "" pythonw "%~dp0RoR2_Unlocker_GUI.py"
if %errorlevel% neq 0 (
    start "" python "%~dp0RoR2_Unlocker_GUI.py"
)
exit
