"""Send only the approved fictional promo copy to free Edge TTS."""
from pathlib import Path
import asyncio,json,subprocess,importlib.metadata
import edge_tts

root=Path(__file__).resolve().parents[1]
script=json.loads((root/'work/voiceover-script.json').read_text())
out=root/'work/audio-raw';out.mkdir(exist_ok=True)

def duration(p):
 return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(p)],text=True))

async def main():
 results=[]
 for s in script['segments']:
  p=out/f"voice-{s['id']}.mp3"
  if not p.exists() or p.stat().st_size<1000:
   tts=edge_tts.Communicate(s['text'],script['voice'],rate=script['rate'],pitch=script['pitch'],connect_timeout=15,receive_timeout=35)
   with p.open('wb') as f:
    async for chunk in tts.stream():
     if chunk['type']=='audio':f.write(chunk['data'])
  seconds=duration(p)
  available=s['latest_end']-s['start']-.12
  results.append({**s,'raw_file':str(p.relative_to(root)),'raw_seconds':seconds,'available_seconds':available,'needs_fit':seconds>available})
  print(json.dumps({'id':s['id'],'seconds':seconds,'available':round(available,3),'fits':seconds<=available}),flush=True)
 (root/'work/voice-generation.json').write_text(json.dumps({'engine':'rany2/edge-tts','version':importlib.metadata.version('edge-tts'),'voice':script['voice'],'rate':script['rate'],'transmission':'fictional promotional copy only','segments':results},ensure_ascii=False,indent=2)+'\n')

asyncio.run(main())
