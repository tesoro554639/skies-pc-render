@echo off
cd /d %~dp0
set FILM=%1
if "%FILM%"=="" set FILM=knocker-upper
echo Switching to CPU (SwiftShader) render mode...
copy /Y tools\render\run.js.cpu tools\render\run.js >nul 2>&1
python run_loop.py films\%FILM% --mode cpu %2 %3 %4 %5
pause
