@echo off
cd /d %~dp0
set FILM=%1
if "%FILM%"=="" set FILM=knocker-upper
python encode_film.py films\%FILM% %2 %3 %4 %5
pause
