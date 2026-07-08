@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [Honey-Finder] .venv was not found.
  echo Run setup first:
  echo python -m venv .venv
  echo .\.venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)

if not exist ".env" (
  echo [Honey-Finder] .env was not found.
  echo Copy .env.example to .env and add your Discord bot token.
  pause
  exit /b 1
)

echo [Honey-Finder] Starting Discord bot...
echo Keep this window open while the bot is running.
echo.
".venv\Scripts\python.exe" -m src.bot

echo.
echo [Honey-Finder] Bot stopped.
pause
