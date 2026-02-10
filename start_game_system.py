"""
Start the complete game system:
1. Django web server
2. Game engine (auto-start games and call numbers)
3. Telegram bot
"""
import subprocess
import sys
import os
import time

def main():
    print("=" * 60)
    print("🎮 ETHIO BINGO GAME SYSTEM")
    print("=" * 60)
    print()
    
    processes = []
    
    try:
        # Start Django server
        print("🌐 Starting Django web server on port 8000...")
        django_process = subprocess.Popen(
            [sys.executable, 'manage.py', 'runserver', '8000'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        processes.append(('Django', django_process))
        time.sleep(2)
        
        # Start Game Engine
        print("🎮 Starting Game Engine...")
        engine_process = subprocess.Popen(
            [sys.executable, 'manage.py', 'run_game_engine'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        processes.append(('Game Engine', engine_process))
        time.sleep(2)
        
        # Start Telegram Bot
        print("🤖 Starting Telegram Bot...")
        bot_process = subprocess.Popen(
            [sys.executable, 'start_bot.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        processes.append(('Bot', bot_process))
        
        print()
        print("=" * 60)
        print("✅ ALL SYSTEMS RUNNING")
        print("=" * 60)
        print()
        print("📊 System Status:")
        print("  • Django Server: http://localhost:8000")
        print("  • Game Engine: Active")
        print("  • Telegram Bot: Active")
        print()
        print("Press Ctrl+C to stop all services")
        print("=" * 60)
        print()
        
        # Keep running and show output
        while True:
            for name, process in processes:
                if process.poll() is not None:
                    print(f"⚠️  {name} stopped unexpectedly!")
                    raise KeyboardInterrupt
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n⏹  Stopping all services...")
        for name, process in processes:
            print(f"  Stopping {name}...")
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        print("✅ All services stopped")

if __name__ == '__main__':
    main()
