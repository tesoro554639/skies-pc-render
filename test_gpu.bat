@echo off
cd /d %~dp0
echo Test: rendering 5 frames on GPU. Compare the new frame with a CPU frame when done.
python tools\render\render.py --web films\knocker-upper\engine\web --out films\knocker-upper\test_gpu --list 200,201,202,203,204 --w 540 --procs 1 --ms 1 --sm 2048
pause
