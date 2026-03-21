"""
Start Telegram bot only in development mode.
"""
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def main() -> int:
    os.chdir(BASE_DIR)
    os.environ.setdefault("DJANGO_ENV", "development")

    command = [sys.executable, "start_bot.py"]
    return subprocess.call(command, cwd=str(BASE_DIR))


if __name__ == "__main__":
    raise SystemExit(main())
