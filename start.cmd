@echo off
setlocal
cd /d "%~dp0"

where docker >nul 2>&1
if errorlevel 1 (
  echo Instale o Docker Desktop, abra ele e espere o icone ficar verde.
  echo https://www.docker.com/products/docker-desktop/
  pause
  exit /b 1
)

where wsl >nul 2>&1
if not errorlevel 1 (
  wsl -e bash ./dev up -d
  goto :done
)

where bash >nul 2>&1
if not errorlevel 1 (
  bash ./dev up -d
  goto :done
)

echo Precisa do WSL ou do Git Bash, alem do Docker Desktop.
pause
exit /b 1

:done
echo.
echo Se deu certo, abra: http://localhost/launchpad
pause
