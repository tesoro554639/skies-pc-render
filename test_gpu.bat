@echo off
cd /d %~dp0
set FILM=%1
if "%FILM%"=="" set FILM=knocker-upper
echo Testing 5 frames on GPU for films\%FILM%...
copy /Y tools\render\run.js.gpu tools\render\run.js >nul 2>&1
python tools\render\render.py --web films\%FILM%\engine\web --out films\%FILM%\test_gpu --list 200,201,202,203,204 --w 540 --procs 1 --ms 1 --sm 2048 --mode gpu
pause
