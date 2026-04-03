@echo off
:: Start the Wavy Labs AI backend (Windows)
cd /d "%~dp0"
python server.py %*
