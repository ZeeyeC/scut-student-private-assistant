"""Record real macOS UI against disposable data; never use the personal backend."""
import argparse
import json
import os
import plistlib
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parent
project = root.parent
parser = argparse.ArgumentParser()
parser.add_argument('--seconds', type=int, default=60)
args = parser.parse_args()
if not 50 <= args.seconds <= 180:
    raise SystemExit('Recording duration must be between 50 and 180 seconds')
output = root / 'build/recording'
output.mkdir(parents=True, exist_ok=True)
for name in ['recording-ready.json', 'recording-error.txt', 'demo-flow-passed.txt', 'recording-result.json']:
    (output / name).unlink(missing_ok=True)
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    opener.open('http://127.0.0.1:5189/api/healthz', timeout=1)
except OSError:
    pass
else:
    raise SystemExit('5189 is occupied; will not touch another service')

app = output / '奶蛙 Demo2.2 演示.app'
if app.exists():
    shutil.rmtree(app)
shutil.copytree(root / 'dist/课间桌宠.app', app, symlinks=True)
info = app / 'Contents/Info.plist'
data = plistlib.loads(info.read_bytes())
data.update(CFBundleIdentifier='cn.campuscompanion.demo22', CFBundleName='奶蛙 Demo2.2 演示', CFBundleDisplayName='奶蛙 Demo2.2 演示')
info.write_bytes(plistlib.dumps(data))
subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(app)], check=True)

with tempfile.TemporaryDirectory(prefix='campus-pet-recording-') as temporary:
    data = Path(temporary)
    (data / '.pet-smoke-isolated').touch()
    environment = {**os.environ, 'PET_TEST_DATA': str(data), 'PYTHONPATH': str(project / 'backend') + os.pathsep + str(root / 'tests')}
    with (output / 'server.log').open('w') as server_log, (output / 'native.log').open('w') as native_log, (output / 'capture.log').open('w') as capture_log:
        server = subprocess.Popen([str(project / 'backend/.venv/bin/python'), str(root / 'tests/smoke_server.py')], cwd=root, env=environment, stdout=server_log, stderr=subprocess.STDOUT)
        native = recorder = None
        try:
            for _ in range(100):
                try:
                    with opener.open('http://127.0.0.1:5189/api/healthz', timeout=1) as response:
                        assert json.load(response)['model_configured'] is False
                    break
                except OSError:
                    if server.poll() is not None:
                        raise RuntimeError('Disposable server exited; inspect server.log')
                    time.sleep(.1)
            else:
                raise RuntimeError('Disposable server startup timed out')
            native = subprocess.Popen([str(app / 'Contents/MacOS/CampusPet'), '--external-service', '--port', '5189', '--data-dir', str(data), '--smoke-test', str(output), '--record-demo'], stdout=native_log, stderr=subprocess.STDOUT)
            for _ in range(300):
                if (output / 'recording-ready.json').exists():
                    break
                if native.poll() is not None or (output / 'recording-error.txt').exists():
                    raise RuntimeError('Demo setup failed; inspect recording-error.txt and native.log')
                time.sleep(.1)
            else:
                raise RuntimeError('Demo setup timed out')
            ready = json.loads((output / 'recording-ready.json').read_text())
            movie = output / 'Demo2.2-raw.mov'
            movie.unlink(missing_ok=True)
            command = ['/usr/sbin/screencapture', '-v', '-k', '-V', str(args.seconds), '-R' + ','.join(map(str, ready['rect'])), str(movie)]
            recorder = subprocess.Popen(command, stdout=capture_log, stderr=subprocess.STDOUT)
            print(json.dumps({'recording': True, 'bundle_id':ready['bundle_id'], 'rect':ready['rect'], 'seconds':args.seconds}, ensure_ascii=False), flush=True)
            started = time.monotonic()
            while recorder.poll() is None:
                time.sleep(.2)
            recorder.wait(timeout=15)
            if not movie.exists() or movie.stat().st_size < 1024:
                raise RuntimeError('macOS screen recording did not produce a movie; inspect capture.log and screen recording permission')
            if not (output / 'demo-flow-passed.txt').exists():
                raise RuntimeError('Recorded flow did not finish; inspect recording-error.txt')
            result = {'recorded': True, 'recorder':'macOS screencapture -v', 'movie':movie.name, 'bytes':movie.stat().st_size, 'elapsed_seconds':round(time.monotonic()-started,2), 'isolated_data':True, 'audio':False, 'guided_flow_passed':True}
            (output / 'recording-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
            print(json.dumps(result, ensure_ascii=False), flush=True)
        finally:
            if recorder is not None and recorder.poll() is None:
                recorder.terminate(); recorder.wait(timeout=10)
            if native is not None and native.poll() is None:
                native.terminate(); native.wait(timeout=10)
            if server.poll() is None:
                server.terminate()
            server.wait(timeout=15)
