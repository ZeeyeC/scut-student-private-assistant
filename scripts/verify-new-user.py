"""Run a copied portable App with empty isolated data; never touch another service."""
import argparse,hashlib,json,os,shutil,subprocess,tempfile,time
from pathlib import Path
import httpx
from app.launcher import desktop_config,service_identity

parser=argparse.ArgumentParser();parser.add_argument('--app',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
origin='http://127.0.0.1:5173'
with httpx.Client(base_url=origin,trust_env=False,timeout=10) as client:
    try:client.get('/api/healthz',timeout=1)
    except httpx.ConnectError:pass
    else:raise SystemExit('5173 occupied; existing service preserved, first-run simulation not started')
    with tempfile.TemporaryDirectory(prefix='campus-new-user-') as directory:
        root=Path(directory);app=root/'Applications/课间桌宠.app';shutil.copytree(args.app,app,symlinks=True)
        resources=app/'Contents/Resources';assert not (resources/'source-project.txt').exists()
        data=root/'empty-user-data';data.mkdir();assert not list(data.iterdir())
        service=resources/'service';embedded=service/'_internal';expected=service_identity(desktop_config(data,embedded,project=False))
        process=subprocess.Popen([str(app/'Contents/MacOS/CampusPet'),'--data-dir',str(data)],cwd=data,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        owned=False
        try:
            for _ in range(300):
                if process.poll() is not None:raise RuntimeError('Copied App exited before first launch; another running App may own the bundle ID')
                try:
                    health=client.get('/api/healthz',timeout=1).json()
                    if any(health.get(k)!=v for k,v in expected.items()):raise RuntimeError('Service identity differs; no data changed')
                    owned=True;assert health['model_configured'] is False;break
                except httpx.ConnectError:time.sleep(.2)
            else:raise RuntimeError('Fresh App startup timed out')
            csrf=client.get('/api/csrf').json()['csrf_token'];headers={'Origin':origin,'X-CSRF-Token':csrf}
            response=client.post('/api/local/session',json={},headers=headers);response.raise_for_status()
            installation=client.get('/api/local/extension-installation');installation.raise_for_status();info=installation.json()
            destination=data/'desktop-extension';assert info['available'] and Path(info['directory'])==destination
            source=embedded/'extension/.output/chrome-mv3';count=0
            for path in source.rglob('*'):
                if path.is_file():
                    assert hashlib.sha256(path.read_bytes()).digest()==hashlib.sha256((destination/path.relative_to(source)).read_bytes()).digest();count+=1
            assert count>1
            assert client.get('/api/tasks').json()==[] and client.get('/api/courses').json()==[]
            result={'passed':True,'scope':'Copied actual App + bundled frozen backend; empty isolated data; no developer source linkage; no paid model calls','extension_version':info['version'],'extension_files_verified':count,'checks':['portable bundle has no source-project marker','App starts from copied location','fresh local SQLite identity','no tasks or courses from developer','extension extracted to fixed user directory','all extracted extension hashes equal bundled files'],'limits':['Same macOS account with an empty explicit data directory, not a new OS account','No real school credentials or genuine school timetable acceptance']}
            args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
        finally:
            if owned:
                try:
                    csrf=client.get('/api/csrf').json()['csrf_token'];client.post('/api/local/session',json={},headers={'Origin':origin,'X-CSRF-Token':csrf}).raise_for_status()
                    client.post('/api/local/shutdown',json={},headers={'Origin':origin,'X-CSRF-Token':csrf}).raise_for_status()
                    for _ in range(100):
                        try:client.get('/api/healthz',timeout=1);time.sleep(.1)
                        except httpx.ConnectError:break
                except Exception as error:raise RuntimeError('Could not shut down the isolated first-run backend') from error
            if process.poll() is None:process.terminate();process.wait(timeout=15)
