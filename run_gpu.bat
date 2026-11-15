@echo off
cd /d %~dp0
echo Switching to GPU (RTX 3050, DirectX 11) render...
copy /Y tools\render\run.js.gpu tools\render\run.js
python run_loop.py films\knocker-upper
pause
