"""Start frontend server"""
import subprocess
import os

frontend_dir = r"D:\JARVES\omnicheat-pro\frontend"

proc = subprocess.Popen(
    ["npm", "run", "dev"],
    cwd=frontend_dir,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    shell=True,
)

print(f"Frontend starting... PID: {proc.pid}")

# Wait and read output
import time
time.sleep(5)

# Check if process is still running
if proc.poll() is None:
    print("Frontend is running!")
    print("Open: http://localhost:3000")
else:
    stdout, stderr = proc.communicate()
    print(f"Failed: {stderr}")
