@echo off
cd /d %~dp0
echo Reverting to CPU (SwiftShader) render...
copy /Y tools\render\run.js.cpu tools\render\run.js
python run_loop.py films\knocker-upper
pause
