@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" || exit /b 1

docker compose version >nul 2>&1
if errorlevel 1 (
    echo Install Docker Desktop with Docker Compose, then run this file again.
    goto :failed
)
docker info >nul 2>&1
if errorlevel 1 (
    echo Start Docker Desktop and wait for its engine to be ready, then try again.
    goto :failed
)
if not exist ".env" (
    copy /y ".env.example" ".env" >nul || goto :failed
    echo Created .env. Add a Gemini key there to enable AI investigations.
)

echo Starting Sentinel AI. The first build may take several minutes.
docker compose up --build --wait --wait-timeout 180
if errorlevel 1 (
    echo Startup failed. Run "docker compose logs" in this folder for details.
    goto :failed
)

echo Sentinel AI is ready at http://localhost:8000/docs
start "" "http://localhost:8000/docs"
popd
exit /b 0

:failed
pause
popd
exit /b 1
