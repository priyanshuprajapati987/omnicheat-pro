"""Start server detached - runs independently"""
import subprocess
import os

backend_dir = r"D:\JARVES\omnicheat-pro\backend"
python_exe = os.path.join(backend_dir, "venv", "Scripts", "python.exe")

# Start completely detached
proc = subprocess.Popen(
    [python_exe, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"],
    cwd=backend_dir,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    stdin=subprocess.DEVNULL,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
)

print(f"PID: {proc.pid}")
# Don't wait - just exit
proc.poll()
