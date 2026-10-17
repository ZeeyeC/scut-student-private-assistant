"""Exercise native WebKit with real isolated API/SQLite, leaving production alone."""
import json
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parent
project = root.parent
output = root / "build/verification"
output.mkdir(parents=True, exist_ok=True)
result_path = output / "result.json"
result_path.unlink(missing_ok=True)
python = project / "backend/.venv/bin/python"
app = root / "dist/课间桌宠.app/Contents/MacOS/CampusPet"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    opener.open("http://127.0.0.1:5189/api/healthz", timeout=1)
except OSError:
    pass
else:
    raise SystemExit("5189 is occupied; never reuse or stop an unrelated service.")
with tempfile.TemporaryDirectory(prefix="campus-pet-smoke-") as temporary:
    data = Path(temporary)
    (data / ".pet-smoke-isolated").touch()
    environment = {**os.environ, "PET_TEST_DATA": str(data), "PYTHONPATH": str(project / "backend") + os.pathsep + str(root / "tests")}
    with (output / "server.log").open("w") as server_log, (output / "native.log").open("w") as native_log:
        server = subprocess.Popen([str(python), "-m", "uvicorn", "smoke_server:app", "--host", "127.0.0.1", "--port", "5189"], cwd=root, env=environment, stdout=server_log, stderr=subprocess.STDOUT)
        native = None
        try:
            for _ in range(100):
                try:
                    with opener.open("http://127.0.0.1:5189/api/healthz", timeout=1) as response:
                        assert json.load(response)["model_configured"] is False
                        break
                except OSError:
                    if server.poll() is not None:
                        raise RuntimeError("Test server exited; inspect server.log")
                    time.sleep(0.1)
            else:
                raise RuntimeError("Test server startup timed out")
            native = subprocess.Popen([str(app), "--external-service", "--port", "5189", "--data-dir", str(data), "--smoke-test", str(output)], stdout=native_log, stderr=subprocess.STDOUT)
            native.wait(timeout=100)
            result = json.loads(result_path.read_text())
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if not result["passed"]:
                raise SystemExit(1)
        finally:
            if native is not None and native.poll() is None:
                native.terminate(); native.wait(timeout=10)
            server.terminate(); server.wait(timeout=15)
