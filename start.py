"""Startup script — launches backend + frontend together."""
import subprocess
import sys
import os
import time
import webbrowser

PROJECT = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(PROJECT, "backend")
FRONTEND = os.path.join(PROJECT, "frontend")

# Start backend
backend = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app",
     "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning"],
    cwd=BACKEND,
)

# Start frontend (cwd must be frontend/ so Streamlit finds pages/)
frontend = subprocess.Popen(
    [sys.executable, "-m", "streamlit", "run", "app.py",
     "--server.port", "8501", "--server.headless", "true"],
    cwd=FRONTEND,
)

print("=" * 50)
print("  408考研AI助教 已启动")
print("  Backend:  http://127.0.0.1:8000")
print("  Frontend: http://127.0.0.1:8501")
print("  API文档:  http://127.0.0.1:8000/docs")
print("  按 Ctrl+C 停止")
print("=" * 50)

time.sleep(3)
webbrowser.open("http://127.0.0.1:8501")

try:
    backend.wait()
except KeyboardInterrupt:
    print("\n正在关闭...")
    backend.terminate()
    frontend.terminate()
