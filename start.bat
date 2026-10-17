@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -c "import numpy, shapely, mapbox_earcut, PIL" >nul 2>&1
if errorlevel 1 (
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m tag_generator %*
if errorlevel 1 goto failed
exit /b 0
:failed
echo Start fehlgeschlagen. Bitte die Hinweise oben und die README pruefen.
pause
exit /b 1
