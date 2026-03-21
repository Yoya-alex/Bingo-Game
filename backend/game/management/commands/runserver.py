import atexit
import os
import signal
import subprocess
import sys
from pathlib import Path

from django.core.management.commands.runserver import Command as DjangoRunserverCommand


class Command(DjangoRunserverCommand):
    help = "Starts Django server. Set AUTO_START_GAME_SERVICES=1 to auto-start game engine and bot."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._aux_processes = []
        self._aux_started = False

    def inner_run(self, *args, **options):
        self._maybe_start_aux_processes(options)
        try:
            return super().inner_run(*args, **options)
        finally:
            self._stop_aux_processes()

    def _maybe_start_aux_processes(self, options):
        if self._aux_started:
            return

        # In autoreload mode, only start children from the reloader child process.
        if options.get("use_reloader", True) and os.environ.get("RUN_MAIN") != "true":
            return

        if not self._auto_start_enabled():
            self.stdout.write(self.style.WARNING("[startup] Auto-start disabled by AUTO_START_GAME_SERVICES."))
            return

        base_dir = Path(__file__).resolve().parents[3]

        self._start_process(
            name="Game Engine",
            command=[sys.executable, "manage.py", "run_game_engine"],
            cwd=base_dir,
        )
        self._start_process(
            name="Bot",
            command=[sys.executable, "start_bot.py"],
            cwd=base_dir,
        )

        atexit.register(self._stop_aux_processes)
        signal.signal(signal.SIGTERM, self._signal_stop)
        signal.signal(signal.SIGINT, self._signal_stop)

        self._aux_started = True
        self.stdout.write(self.style.SUCCESS("[startup] Game Engine and Bot started."))

    def _auto_start_enabled(self):
        value = os.environ.get("AUTO_START_GAME_SERVICES", "0").strip().lower()
        return value in {"1", "true", "yes", "on"}

    def _start_process(self, name, command, cwd):
        process = subprocess.Popen(command, cwd=str(cwd))
        self._aux_processes.append((name, process))
        self.stdout.write(f"[startup] {name} started (pid={process.pid}).")

    def _stop_aux_processes(self):
        if not self._aux_processes:
            return

        for name, process in reversed(self._aux_processes):
            if process.poll() is not None:
                continue

            self.stdout.write(f"[startup] Stopping {name} (pid={process.pid})...")
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

        self._aux_processes = []

    def _signal_stop(self, signum, _frame):
        self.stdout.write(self.style.WARNING(f"[startup] Received signal {signum}, shutting down child services."))
        self._stop_aux_processes()
