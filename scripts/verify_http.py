"""Start isolated local servers, verify HTTP readiness, then stop owned processes."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from uuid import uuid4

root = Path(__file__).resolve().parents[1]
runtime = root / '.test-tmp-http' / str(uuid4())
runtime.mkdir(parents=True)
env = os.environ.copy()
env['PYTHONPATH'] = str(root / 'backend')
env['DATABASE_URL'] = 'sqlite:///' + str(runtime / 'smoke.db').replace('\\', '/')
flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
subprocess.run([sys.executable, '-m', 'alembic', '-c', 'backend/alembic.ini', 'upgrade', 'head'], cwd=root, env=env, check=True, creationflags=flags)

def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

def ready(url, process):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('Server exited before HTTP readiness')
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return response.read().decode()
        except (OSError, TimeoutError):
            time.sleep(.2)
    raise RuntimeError('HTTP readiness timed out')

processes = []
try:
    backend_port, frontend_port = free_port(), free_port()
    with (runtime / 'backend.log').open('w') as backend_log, (runtime / 'frontend.log').open('w') as frontend_log:
        backend = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(backend_port)], cwd=root, env=env, stdout=backend_log, stderr=subprocess.STDOUT, creationflags=flags)
        processes.append(backend)
        health = json.loads(ready(f'http://127.0.0.1:{backend_port}/api/v1/health/database', backend))
        frontend = subprocess.Popen([shutil.which('node') or 'node', 'node_modules/vite/bin/vite.js', 'preview', '--host', '127.0.0.1', '--port', str(frontend_port)], cwd=root / 'frontend', stdout=frontend_log, stderr=subprocess.STDOUT, creationflags=flags)
        processes.append(frontend)
        html = ready(f'http://127.0.0.1:{frontend_port}', frontend)
        assert health['status'] == 'ok'
        assert 'Aegis | Banking Operations' in html
        result = {'backend_database_health': 'HTTP 200', 'frontend_preview': 'HTTP 200', 'browser_interaction_verified': False}
        (root / 'evaluation/results/http_smoke.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result))
finally:
    for process in reversed(processes):
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
