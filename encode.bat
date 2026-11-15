@echo off
cd /d %~dp0
set FILM=%1
if "%FILM%"=="" set FILM=knocker-upper
python encode_film.py films\%FILM%
pause
