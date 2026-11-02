"""One authorized real vision call; prints only safe exception categories."""
from pathlib import Path
import sys,json,asyncio,httpx
from datetime import datetime
repo=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(repo/'backend'))
from app.launcher import desktop_config,service_identity
from app.model_gateway import ModelGateway
root=Path(__file__).resolve().parent
resources=Path.home()/'ProjectManagement/Demo2.9/课间桌宠.app/Contents/Resources/service/_internal'
config=desktop_config(root/'profile',resources,project=False)
c=httpx.Client(base_url='http://127.0.0.1:5173',trust_env=False)
health=c.get('/api/healthz').raise_for_status().json()
assert health['database_id']==service_identity(config)['database_id']
csrf=c.get('/api/csrf').json()['csrf_token']
c.post('/api/local/session',json={},headers={'Origin':str(c.base_url).rstrip('/'),'X-CSRF-Token':csrf}).raise_for_status()
courses=c.get('/api/courses').raise_for_status().json()
p=root/'model-requests.json';budget=json.loads(p.read_text());assert budget['used']<budget['authorized_maximum']
budget['used']+=1
entry={'number':budget['used'],'purpose':'诊断真实截图识别失败类别','started':datetime.now().isoformat(),'status':'running'}
budget['requests'].append(entry);p.write_text(json.dumps(budget,ensure_ascii=False,indent=2)+'\n')
async def main():
 gateway=ModelGateway(config)
 try:
  result=await gateway.extract_assignments((repo/'videos/campus-promo-v1/materials/作业通知.png').read_bytes(),'image/png',courses,None)
  entry.update(status='success',item_count=len(result['items']))
  (root/'vision-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 except Exception as e:
  entry.update(status='failed',exception_type=type(e).__name__)
  if getattr(e,'status_code',None):entry['http_status']=e.status_code
  if hasattr(e,'errors'):entry['validation_errors']=[{'loc':v['loc'],'type':v['type']} for v in e.errors()]
  if getattr(e,'body',None):
   body=e.body
   if isinstance(body,dict):
    err=body.get('error',body)
    if isinstance(err,dict):entry['provider_error_code']=err.get('code') or err.get('type')
  print(json.dumps(entry,ensure_ascii=False))
 finally:
  await gateway.aclose()
  p.write_text(json.dumps(budget,ensure_ascii=False,indent=2)+'\n')
asyncio.run(main())
