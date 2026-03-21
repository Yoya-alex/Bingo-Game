"""
Start Django development server only (no bot, no game engine).
"""
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def main() -> int:
    os.chdir(BASE_DIR)
    os.environ.setdefault("DJANGO_ENV", "development")
    os.environ.setdefault("AUTO_START_GAME_SERVICES", "0")

    command = [sys.executable, "manage.py", "runserver", "8000"]
    return subprocess.call(command, cwd=str(BASE_DIR))


if __name__ == "__main__":
    raise SystemExit(main())
