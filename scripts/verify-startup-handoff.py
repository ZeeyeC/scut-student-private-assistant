"""Actual frozen helper + explicit synthetic legacy backend, no personal profile."""
import argparse,json,os,socket,subprocess,tempfile,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import httpx
from app.launcher import desktop_config,service_identity

p=argparse.ArgumentParser();p.add_argument('--app',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
app=args.app.resolve();binary=app/'Contents/Resources/service/CampusCompanion';resources=binary.parent/'_internal'
runtime=json.loads((resources/'service-build.json').read_text());origin='http://127.0.0.1:5173'
env={**os.environ,'PYINSTALLER_RESET_ENVIRONMENT':'1'}
result={'passed':False,'scope':'Actual frozen helper and backend; explicit synthetic legacy HTTP; isolated data; no model calls'}
with tempfile.TemporaryDirectory(prefix='campus-handoff-frozen-') as temporary:
    root=Path(temporary);selected=root/'selected';selected.mkdir()
    (selected/'.campus-isolated-acceptance').write_text('isolated\n')
    expected=service_identity(desktop_config(selected,resources,project=False))
    state={'health':{**expected,'database_id':'c'*24},'posts':[],'stops':0}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def response(self,body,status=200,cookie=None):
            self.send_response(status)
            if cookie:self.send_header('Set-Cookie',cookie)
            self.end_headers()
            if status!=204:self.wfile.write(json.dumps(body).encode())
        def do_GET(self):
            if self.path=='/api/healthz':self.response(state['health'])
            elif self.path=='/api/csrf':self.response({'csrf_token':'synthetic-csrf'},cookie='campus_csrf=synthetic-csrf; Path=/')
            elif self.path=='/api/local/status':self.response({'selected':True})
            else:self.response({},404)
        def do_POST(self):
            assert self.headers['Origin']==origin and self.headers['X-CSRF-Token']=='synthetic-csrf'
            assert 'campus_csrf=synthetic-csrf' in self.headers['Cookie']
            assert self.rfile.read(int(self.headers['Content-Length']))==b'{}'
            state['posts'].append(self.path)
            if self.path=='/api/local/session':self.response({},204,'campus_session=synthetic; Path=/')
            elif self.path=='/api/local/shutdown':
                assert 'campus_session=synthetic' in self.headers['Cookie']
                state['stops']+=1;self.response({'stopping':True})
                threading.Thread(target=http.shutdown,daemon=True).start()
            else:self.response({},404)
    # Binding failure aborts; never attach to or replace an unrelated user service.
    http=ThreadingHTTPServer(('127.0.0.1',5173),Handler)
    def run_http():
        try:http.serve_forever(poll_interval=.05)
        finally:http.server_close()
    thread=threading.Thread(target=run_http,daemon=True);thread.start()
    def helper(*options):
        completed=subprocess.run([str(binary),*options,'--no-browser','--data-dir',str(selected)],env=env,capture_output=True,text=True,timeout=45)
        if completed.returncode:raise RuntimeError('Frozen helper rejected: '+completed.stdout[-500:])
        return json.loads(completed.stdout)
    try:
        different=helper('--inspect-service');assert different['state']=='conflict' and different['different_data'] and different['old_version']
        assert state['posts']==[],'Inspection/cancel must be read-only'
        state['health']={**expected}
        same=helper('--inspect-service');assert same['state']=='conflict' and not same['different_data'] and same['old_version']
        # A stale approval for the previous data identity must fail before POST.
        stale=subprocess.run([str(binary),'--handoff-service',different['token'],'--no-browser','--data-dir',str(selected)],env=env,capture_output=True,text=True,timeout=45)
        assert stale.returncode!=0 and state['posts']==[]
        assert helper('--handoff-service',same['token'])=={'stopped':True}
        thread.join(timeout=5);assert not thread.is_alive() and state['stops']==1
    finally:
        if thread.is_alive():http.shutdown();thread.join(timeout=5);http.server_close()
    process=subprocess.Popen([str(binary),'--serve','--data-dir',str(selected)],env=env,cwd=selected,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        with httpx.Client(base_url=origin,trust_env=False,timeout=2) as client:
            for _ in range(300):
                if process.poll() is not None:raise RuntimeError('Frozen replacement exited')
                try:
                    health=client.get('/api/healthz').json()
                    assert all(health.get(k)==v for k,v in expected.items())
                    assert health['runtime_id']==runtime['runtime_id'] and health['app_version']==runtime['app_version']
                    break
                except httpx.ConnectError:time.sleep(.1)
            else:raise RuntimeError('Replacement failed to start')
            assert helper('--inspect-service')['state']=='compatible'
            csrf=client.get('/api/csrf').json()['csrf_token'];headers={'Origin':origin,'X-CSRF-Token':csrf}
            client.post('/api/local/session',json={},headers=headers).raise_for_status()
            assert client.get('/api/tasks').json()==[]
            client.post('/api/local/shutdown',json={},headers=headers).raise_for_status()
            process.wait(timeout=15)
        result.update(passed=True,different_profile_conflict=True,same_profile_old_build_conflict=True,
                      inspection_has_no_mutations=True,stale_handoff_rejected=True,legacy_204_session=True,
                      graceful_stop_count=state['stops'],replacement_database_identity=True,replacement_runtime_identity=True)
    finally:
        if process.poll() is None:process.terminate();process.wait(timeout=15)
args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
