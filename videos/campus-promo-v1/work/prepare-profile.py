"""Copy only model settings into an ignored, disposable demo profile."""
from pathlib import Path
import os, sys
from dotenv import dotenv_values

repo=Path(__file__).resolve().parents[3]
target=Path(__file__).resolve().parent/'profile'
target.mkdir(exist_ok=True)
(target/'.campus-isolated-acceptance').touch()
source=repo/'.env'
if not source.exists():
    source=Path.home()/'ProjectManagement/agentbuild/.env'
if not source.exists():
    raise SystemExit('Current model configuration not found; nothing copied.')
allowed={'model_provider','text_model','vision_model','model_api_key','model_base_url','model_use_system_proxy'}
values={k.lower():v for k,v in dotenv_values(source).items() if k.lower() in allowed and v is not None}
if not values.get('model_api_key'):
    raise SystemExit('No configured model credential; nothing copied.')
file=target/'model.env'
import json
file.write_text(''.join(k.upper()+'='+json.dumps(v,ensure_ascii=False)+'\n' for k,v in values.items()))
os.chmod(file,0o600)
print('Prepared isolated profile with model settings only; no business records copied.')
