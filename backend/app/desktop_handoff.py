"""Version-aware, explicit graceful handoff between local desktop bundles."""
import hashlib
import hmac
import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

HEX = re.compile(r'^[0-9a-f]{64}$')
VERSION = re.compile(r'^(?:[0-9]+(?:\.[0-9]+){1,3}|dev)$')


def runtime_manifest(resources: Path) -> dict:
    resources=Path(resources)
    manifest=resources/'service-build.json'
    if manifest.is_file():
        body=json.loads(manifest.read_text(encoding='utf-8'))
        if isinstance(body,dict) and HEX.fullmatch(str(body.get('runtime_id',''))) and VERSION.fullmatch(str(body.get('app_version',''))):
            return {key:body[key] for key in ('runtime_id','app_version')}
        raise RuntimeError('应用构建信息不完整，请重新安装最新版。')
    if getattr(sys,'frozen',False):
        raise RuntimeError('应用缺少构建信息，请重新安装最新版。')
    version_file=resources/'campus-pet/VERSION'
    version=version_file.read_text().strip() if version_file.is_file() else 'dev'
    if not VERSION.fullmatch(version): raise RuntimeError('应用版本无效。')
    digest=hashlib.sha256(('campus-runtime-v1:'+version).encode())
    for directory,pattern in [('backend/app','*.py'),('frontend/dist','*')]:
        for path in sorted((resources/directory).rglob(pattern)):
            if not path.is_file() or path.is_symlink(): continue
            digest.update(path.relative_to(resources).as_posix().encode()+b'\0')
            digest.update(path.read_bytes())
    return {'runtime_id':digest.hexdigest(),'app_version':version}


def observed_token(health: dict) -> str:
    if (not isinstance(health,dict) or health.get('application')!='campus-companion'
        or type(health.get('desktop_protocol')) is not int or health['desktop_protocol']!=1
        or health.get('mode')!='local' or not re.fullmatch(r'[0-9a-f]{24}',str(health.get('database_id','')))):
        raise RuntimeError('端口不是可切换的本机课间服务。')
    fields={key:health[key] for key in ('application','desktop_protocol','mode','database_id')}
    for key,pattern in [('runtime_id',HEX),('app_version',VERSION),('instance_id',re.compile(r'^[0-9a-f]{32}$'))]:
        if key not in health: continue
        if not isinstance(health[key],str) or not pattern.fullmatch(health[key]):
            raise RuntimeError('后台身份信息无效，未停止任何服务。')
        fields[key]=health[key]
    return hashlib.sha256(json.dumps(fields,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def inspect_service(selected_identity: dict, probe, runtime: dict) -> dict:
    try:
        health=probe()
        if health is None: return {'state':'absent'}
        token=observed_token(health)
    except Exception:
        return {'state':'foreign'}
    different=health['database_id']!=selected_identity['database_id']
    old=health.get('runtime_id')!=runtime['runtime_id']
    if not different and not old: return {'state':'compatible'}
    return {'state':'conflict','token':token,'different_data':different,'old_version':old,
            'observed_version':health.get('app_version','旧版本')}


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def stop_observed_service(token: str, probe, origin='http://127.0.0.1:5173',timeout=15) -> None:
    if not isinstance(token,str) or not HEX.fullmatch(token): raise RuntimeError('切换请求无效，请重新连接。')
    parsed=urlsplit(origin)
    if (parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or parsed.username or parsed.password
        or parsed.path or parsed.query or parsed.fragment or not parsed.port or not 1024<=parsed.port<=65535):
        raise RuntimeError('切换仅允许本机课间服务。')
    deadline=time.monotonic()+min(max(timeout,0.1),30)

    def check_identity():
        current=probe()
        if current is None or not hmac.compare_digest(observed_token(current),token):
            raise RuntimeError('后台已变化，未发送停止请求。请重新连接后再切换。')
    check_identity()
    cookies=http.cookiejar.CookieJar()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(cookies),NoRedirects())

    def request(path,body=None,csrf=None):
        remaining=deadline-time.monotonic()
        if remaining<=0: raise RuntimeError('切换超时，旧资料已保留，请稍后重试。')
        headers={'Origin':origin,'Accept':'application/json'}
        if body is not None:
            headers.update({'Content-Type':'application/json','X-CSRF-Token':csrf})
        req=urllib.request.Request(origin+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:
            with opener.open(req,timeout=min(3,remaining)) as response:
                raw=response.read(65537)
                # FastAPI Users uses a cookie-only 204 login response.
                if response.status==204 and path=='/api/local/session' and not raw:
                    return {}
                if response.status!=200 or len(raw)>65536: raise ValueError('invalid response')
            result=json.loads(raw)
            if not isinstance(result,dict): raise ValueError('invalid body')
            return result
        except urllib.error.HTTPError as exc:
            if exc.code==409 and path.endswith('/shutdown'):
                raise RuntimeError('旧助手仍在处理请求或由终端启动，请完成操作后再切换。') from None
            raise RuntimeError('旧后台拒绝切换，未强制停止。请在旧版本中停止后台后重试。') from None
        except (OSError,ValueError,urllib.error.URLError):
            raise RuntimeError('旧后台未能完成切换，原资料已保留。请重新连接。') from None

    def csrf_token():
        value=request('/api/csrf').get('csrf_token')
        if not isinstance(value,str) or not value or len(value)>256:
            raise RuntimeError('无法建立旧后台会话，未发送停止请求。')
        return value

    csrf=csrf_token()
    if request('/api/local/status').get('selected') is not True:
        raise RuntimeError('旧版本尚未选定资料，请在旧版本中正常退出后重试。')
    check_identity()
    request('/api/local/session',{},csrf)
    csrf=csrf_token()
    check_identity()
    if request('/api/local/shutdown',{},csrf).get('stopping') is not True:
        raise RuntimeError('旧后台没有接受停止请求，请重试。')
    while time.monotonic()<deadline:
        current=probe()
        if current is None: return
        if not hmac.compare_digest(observed_token(current),token):
            raise RuntimeError('后台已变化，请重新连接；未再发送停止请求。')
        time.sleep(0.1)
    raise RuntimeError('旧后台尚未停止，原资料已保留，请稍后重试。')
