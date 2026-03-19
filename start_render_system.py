import os
import signal
import subprocess
import sys
import threading
import time


def _stream_logs(name: str, process: subprocess.Popen) -> None:
    if process.stdout is None:
        return
    for line in process.stdout:
        print(f"[{name}] {line.rstrip()}", flush=True)


def _start_process(name: str, command: list[str]) -> tuple[str, subprocess.Popen]:
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


def _stop_all(processes: list[tuple[str, subprocess.Popen]]) -> None:
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

    commands = [
        (
            "web",
            [
                sys.executable,
                "-m",
                "gunicorn",
                "bingo_project.wsgi:application",
                "--bind",
                f"0.0.0.0:{port}",
                "--workers",
                workers,
            ],
        ),
        ("engine", [sys.executable, "manage.py", "run_game_engine"]),
        ("bot", [sys.executable, "start_bot.py"]),
    ]

    processes: list[tuple[str, subprocess.Popen]] = []
    stopping = False

    def _handle_signal(signum, _frame):
        nonlocal stopping
        if stopping:
            return
        stopping = True
        print(f"Received signal {signum}, shutting down all services...", flush=True)
        _stop_all(processes)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        for name, command in commands:
            print(f"Starting {name}: {' '.join(command)}", flush=True)
            processes.append(_start_process(name, command))
            time.sleep(1)

        while not stopping:
            for name, process in processes:
                code = process.poll()
                if code is not None:
                    print(f"{name} exited with code {code}. Stopping remaining services...", flush=True)
                    _stop_all(processes)
                    return code
            time.sleep(1)

    except Exception as exc:
        print(f"Fatal startup error: {exc}", flush=True)
        _stop_all(processes)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
