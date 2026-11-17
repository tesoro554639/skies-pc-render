@echo off
cd /d %~dp0
set FILM=%1
if "%FILM%"=="" set FILM=knocker-upper
echo Switching to GPU render mode...
copy /Y tools\render\run.js.gpu tools\render\run.js >nul 2>&1
python run_loop.py films\%FILM% --mode gpu %2 %3 %4 %5
pause
