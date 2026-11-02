"""Create reviewable CFR clips from visually inspected real source intervals."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import subprocess,json,sys

root=Path(__file__).resolve().parents[1]
out=root/'remotion-app/public/footage'
out.mkdir(exist_ok=True)
# Input times are seconds in the actual retained source, not storyboard guesses.
specs=[
 ('image-input','R02-homework-window-01.mp4',1,4,(1300,310,1200,780)),
 ('image-draft','R02-homework-window-01.mp4',17,5,(640,380,1800,670)),
 ('image-deadline','R02-homework-window-01.mp4',96,4,(640,380,1800,670)),
 ('task-results','R03-planning-window-01.mp4',7,5,(360,440,2100,600)),
 ('calendar-context','R04-library-window-01.mp4',1,3,(310,120,2200,1400)),
 ('planning-draft','R03-planning-window-01.mp4',122,6,(400,600,2120,1000)),
 ('today-results','R04-library-details-window-02.mp4',83,7,(244,145,1070,430)),
 ('library-list','R04-library-window-01.mp4',22,5,(330,100,2200,1000)),
 ('knowledge-answer','R05-memory-pet-window-01.mp4',135,7,(410,430,870,230)),
 ('memory-confirm','R05-memory-pet-window-01.mp4',29,7,(900,200,420,250)),
 ('memory-recall','R05-memory-pet-window-01.mp4',74,4,(245,245,1020,220)),
 ('pet-reveal','R05-memory-pet-window-01.mp4',147,3,(900,400,570,556)),
 ('pet-result','R05-memory-pet-window-01.mp4',150,5,(900,400,570,556)),
]
def process(s):
 name,source,start,duration,crop=s
 dest=out/(name+'.mp4')
 if dest.exists() and '--replace-generated' not in sys.argv:raise RuntimeError('Refusing overwrite: '+name)
 x,y,w,h=crop
 command=['ffmpeg','-y' if '--replace-generated' in sys.argv else '-n','-hide_banner','-loglevel','error','-ss',str(start),'-t',str(duration),'-i',str(root/'source'/source),'-an','-vf',f'crop={w}:{h}:{x}:{y},fps=30,setpts=PTS-STARTPTS,scale=1280:-2,setsar=1,tpad=stop_mode=clone:stop_duration=0.1','-frames:v',str(duration*30),'-c:v','libx264','-preset','fast','-crf','17','-pix_fmt','yuv420p','-threads','2','-movflags','+faststart',str(dest)]
 subprocess.run(command,check=True)
 probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=width,height,r_frame_rate,nb_frames','-show_entries','format=duration','-of','json',str(dest)],text=True))
 expected=duration*30
 assert int(probe['streams'][0]['nb_frames'])==expected,(name,probe)
 return {'id':name,'source':source,'source_start_seconds':start,'source_end_seconds':start+duration,'crop':list(crop),'output':str(dest.relative_to(root)),'frames':expected,'fps':30,'probe':probe,'status':'trimmed_pending_final_visual_review'}
selected=specs
if '--only' in sys.argv:
 names=set(sys.argv[sys.argv.index('--only')+1].split(','))
 selected=[s for s in specs if s[0] in names]
 assert len(selected)==len(names),'Unknown clip name'
with ThreadPoolExecutor(max_workers=2) as pool:
 results=list(pool.map(process,selected))
if selected is not specs and (root/'work/cuts.json').exists():
 merged={x['id']:x for x in json.loads((root/'work/cuts.json').read_text())}
 merged.update({x['id']:x for x in results});results=[merged[s[0]] for s in specs]
(root/'work/cuts.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
print('Created and duration-checked',len(selected),'clips;',len(results),'clips indexed. Originals unchanged.')
