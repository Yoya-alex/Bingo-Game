import os
import signal
import subprocess
import sys
import threading
import time
from typing import List, Tuple, Optional


def _stream_logs(name: str, process: subprocess.Popen) -> None:
    if process.stdout is None:
        return
    for line in process.stdout:
        print(f"[{name}] {line.rstrip()}", flush=True)


def _start_process(name: str, command: List[str]) -> Tuple[str, subprocess.Popen]:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    thread = threading.Thread(target=_stream_logs, args=(name, process), daemon=True)
    thread.start()
    return name, process


def _stop_all(processes: List[Tuple[str, subprocess.Popen]]) -> None:
    for name, process in processes:
        if process.poll() is None:
            print(f"Stopping {name}...", flush=True)
            process.terminate()

    deadline = time.time() + 10
    for _, process in processes:
        while process.poll() is None and time.time() < deadline:
            time.sleep(0.2)

    for name, process in processes:
        if process.poll() is None:
            print(f"Force killing {name}...", flush=True)
            process.kill()


def main() -> int:
    port = os.getenv("PORT", "10000")
    workers = os.getenv("WEB_CONCURRENCY", "2")

    print("Ensuring Django superuser from environment...", flush=True)
    subprocess.run([sys.executable, "manage.py", "ensure_superuser"], check=False)

    # Critical: web server must stay alive
    # Non-critical: engine and bot can crash and restart
    web_command = [
        sys.executable, "-m", "gunicorn",
        "bingo_project.wsgi:application",
        "--bind", f"0.0.0.0:{port}",
        "--workers", workers,
    ]
    engine_command = [sys.executable, "manage.py", "run_game_engine"]
    bot_command = [sys.executable, "start_bot.py"]

    processes: List[Tuple[str, subprocess.Popen]] = []
    stopping = False

    def _handle_signal(signum, _frame):
        nonlocal stopping
        if stopping:
            return
        stopping = True
        print(f"Received signal {signum}, shutting down...", flush=True)
        _stop_all(processes)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # Start web server first (critical)
    print(f"Starting web: {' '.join(web_command)}", flush=True)
    web_name, web_proc = _start_process("web", web_command)
    processes.append((web_name, web_proc))
    time.sleep(2)

    # Start engine (non-critical)
    print(f"Starting engine: {' '.join(engine_command)}", flush=True)
    engine_name, engine_proc = _start_process("engine", engine_command)
    processes.append((engine_name, engine_proc))
    time.sleep(1)

    # Start bot (non-critical)
    print(f"Starting bot: {' '.join(bot_command)}", flush=True)
    bot_name, bot_proc = _start_process("bot", bot_command)
    processes.append((bot_name, bot_proc))

    # Track restart counts
    restart_counts = {"engine": 0, "bot": 0}

    try:
        while not stopping:
            # Check web server - if it dies, exit with error
            if web_proc.poll() is not None:
                code = web_proc.returncode
                print(f"[web] Web server exited with code {code}. Shutting down.", flush=True)
                _stop_all(processes)
                return code

            # Check engine - restart if crashed (max 5 times)
            if engine_proc.poll() is not None:
                code = engine_proc.returncode
                print(f"[engine] Game engine exited with code {code}.", flush=True)
                if restart_counts["engine"] < 5:
                    restart_counts["engine"] += 1
                    print(f"[engine] Restarting engine (attempt {restart_counts['engine']})...", flush=True)
                    time.sleep(3)
                    engine_name, engine_proc = _start_process("engine", engine_command)
                    # Update in processes list
                    processes = [(n, p) for n, p in processes if n != "engine"]
                    processes.append((engine_name, engine_proc))
                else:
                    print("[engine] Max restarts reached. Engine will not restart.", flush=True)

            # Check bot - restart if crashed (max 5 times)
            if bot_proc.poll() is not None:
                code = bot_proc.returncode
                print(f"[bot] Bot exited with code {code}.", flush=True)
                if restart_counts["bot"] < 5:
                    restart_counts["bot"] += 1
                    print(f"[bot] Restarting bot (attempt {restart_counts['bot']})...", flush=True)
                    time.sleep(5)
                    bot_name, bot_proc = _start_process("bot", bot_command)
                    processes = [(n, p) for n, p in processes if n != "bot"]
                    processes.append((bot_name, bot_proc))
                else:
                    print("[bot] Max restarts reached. Bot will not restart.", flush=True)

            time.sleep(2)

    except Exception as exc:
        print(f"Fatal error: {exc}", flush=True)
        _stop_all(processes)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
