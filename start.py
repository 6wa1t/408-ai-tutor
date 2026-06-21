"""Startup script — launches backend + frontend together."""
import subprocess
import sys
import os
import time
import shutil
import webbrowser

# ── Python 版本检查 ──
if sys.version_info < (3, 12):
    print(f"错误：需要 Python 3.12+，当前版本是 {sys.version}")
    print("请安装 Python 3.12 或使用正确的 Python 版本运行此脚本")
    sys.exit(1)

PROJECT = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(PROJECT, "backend")
FRONTEND = os.path.join(PROJECT, "frontend")

# ── .env 文件检查 ──
env_path = os.path.join(PROJECT, ".env")
env_example = os.path.join(PROJECT, ".env.example")
if not os.path.exists(env_path) and os.path.exists(env_example):
    shutil.copy(env_example, env_path)
    print("⚠️  未找到 .env 文件，已从 .env.example 自动创建")
    print("   请编辑 .env 文件并填入你的 API Key")

# Fix Windows encoding: force UTF-8 for all subprocesses
env = os.environ.copy()
env["PYTHONUTF8"] = "1"
env["PYTHONIOENCODING"] = "utf-8"

# Start backend
backend = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app",
     "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning"],
    cwd=BACKEND,
    env=env,
)

# Start frontend (cwd must be frontend/ so Streamlit finds pages/)
frontend = subprocess.Popen(
    [sys.executable, "-m", "streamlit", "run", "app.py",
     "--server.port", "8501", "--server.headless", "true"],
    cwd=FRONTEND,
    env=env,
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
