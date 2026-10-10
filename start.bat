@echo off
rem Opens the pet overlay. If it never captures anything, run it as administrator.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" pet_overlay.py
