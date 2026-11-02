import json
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

import pytest
from app import desktop_handoff as h


def health(**changes):
    return {'application':'campus-companion','desktop_protocol':1,'mode':'local','database_id':'a'*24,**changes}


def test_inspection_refuses_old_build_even_with_same_database():
    old=health();selected=health();runtime={'runtime_id':'b'*64}
    assert h.inspect_service(selected,lambda:old,runtime)['state']=='conflict'
    assert h.inspect_service(selected,lambda:health(runtime_id='b'*64),runtime)['state']=='compatible'
    assert h.inspect_service(selected,lambda:health(database_id='c'*24,runtime_id='b'*64),runtime)['different_data']
    assert h.inspect_service(selected,lambda:None,runtime)['state']=='absent'
    for value in [health(mode='shared'),health(application='other'),{},[],health(database_id='secret')]:
        assert h.inspect_service(selected,lambda:value,runtime)=={'state':'foreign'}


def test_build_fingerprint_tracks_runtime_sources_and_version_only(tmp_path):
    (tmp_path/'backend/app').mkdir(parents=True)
    code=tmp_path/'backend/app/a.py';code.write_text('a=1')
    first=h.runtime_manifest(tmp_path)
    (tmp_path/'model.env').write_text('KEY=not-part-of-fingerprint')
    assert h.runtime_manifest(tmp_path)==first
    code.write_text('a=2'); assert h.runtime_manifest(tmp_path)!=first
    (tmp_path/'service-build.json').write_text(json.dumps({'runtime_id':'d'*64,'app_version':'2.8.1'}))
    assert h.runtime_manifest(tmp_path)=={'runtime_id':'d'*64,'app_version':'2.8.1'}


@pytest.fixture
def server():
    state={'health':health(),'posts':[],'busy':False,'selected':True,'redirect':False,'oversize':False,'stops':0}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def reply(self,value,status=200,cookie=None):
            self.send_response(status)
            if cookie:self.send_header('Set-Cookie',cookie)
            self.end_headers();self.wfile.write(json.dumps(value).encode())
        def do_GET(self):
            if state['redirect']:
                self.send_response(302);self.send_header('Location','http://127.0.0.1:1/forbidden');self.end_headers();return
            if self.path=='/api/csrf':self.reply({'csrf_token':'test-csrf'},cookie='campus_csrf=test-csrf; Path=/')
            elif state['oversize']:self.reply({'padding':'x'*65536})
            elif self.path=='/api/local/status':self.reply({'selected':state['selected']})
            else:self.reply({})
        def do_POST(self):
            state['posts'].append(self.path)
            assert self.headers.get('Origin')==state['origin']
            assert self.headers.get('X-CSRF-Token')=='test-csrf'
            assert 'campus_csrf=test-csrf' in self.headers.get('Cookie','')
            assert json.loads(self.rfile.read(int(self.headers['Content-Length'])))=={}
            if self.path=='/api/local/session':
                self.reply({},status=204,cookie='campus_session=synthetic-session; Path=/')
                if state.get('replace'):state['health']=health(instance_id='b'*32)
            elif self.path=='/api/local/shutdown':
                assert 'campus_session=synthetic-session' in self.headers.get('Cookie','')
                if state['busy']:self.reply({'detail':'private body should never echo'},409)
                else:
                    state['stops']+=1;self.reply({'stopping':True})
                    if state.get('replace_after_stop'):state['health']=health(instance_id='c'*32)
                    elif not state.get('persist'):state['health']=None
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    state['origin']='http://127.0.0.1:'+str(http.server_port)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    yield state
    http.shutdown();http.server_close();thread.join()


def stop(state,token=None):
    h.stop_observed_service(token or h.observed_token(health()),lambda:state['health'],origin=state['origin'],timeout=3)


def test_graceful_stop_uses_existing_selected_session_cookie_and_csrf(server):
    stop(server)
    assert server['posts']==['/api/local/session','/api/local/shutdown']
    assert server['stops']==1


@pytest.mark.parametrize('change',[{'selected':False},{'redirect':True},{'oversize':True}])
def test_invalid_onboarding_or_redirect_never_creates_session_or_stops(server,change):
    server.update(change)
    with pytest.raises(RuntimeError):stop(server)
    assert server['posts']==[]


def test_busy_is_not_forced_or_retried(server):
    server['busy']=True
    with pytest.raises(RuntimeError,match='处理请求'):stop(server)
    assert server['stops']==0 and server['posts'].count('/api/local/shutdown')==1


def test_changed_identity_is_rechecked_before_shutdown(server):
    server['replace']=True
    with pytest.raises(RuntimeError,match='后台已变化'):stop(server)
    assert server['posts']==['/api/local/session'] and server['stops']==0


def test_stale_malformed_or_foreign_snapshot_never_mutates(server):
    for token in ['bad','b'*64]:
        with pytest.raises(RuntimeError):stop(server,token)
    server['health']=health(application='other')
    with pytest.raises(RuntimeError):stop(server)
    assert server['posts']==[]


def test_handoff_refuses_non_loopback_before_probe():
    for origin in ['https://127.0.0.1:5173','http://example.com:5173','http://127.0.0.1:5173/path','http://user@127.0.0.1:5173']:
        with pytest.raises(RuntimeError):h.stop_observed_service('b'*64,lambda:pytest.fail('must not probe'),origin=origin)


def test_stop_timeout_and_replacement_never_retry_or_force(server):
    server['persist']=True
    with pytest.raises(RuntimeError,match='尚未停止'):
        h.stop_observed_service(h.observed_token(health()),lambda:server['health'],origin=server['origin'],timeout=0.4)
    assert server['stops']==1
    server['replace_after_stop']=True
    with pytest.raises(RuntimeError,match='后台已变化'):stop(server)
    assert server['stops']==2
