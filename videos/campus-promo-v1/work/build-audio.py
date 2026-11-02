"""Author original music/SFX, fit measured speech, and mix preview stems locally."""
from pathlib import Path
import hashlib,json,math,subprocess,wave
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'remotion-app/public/audio'
OUT.mkdir(exist_ok=True)
CHECK=ROOT/'work/audio-check';CHECK.mkdir(exist_ok=True)
SR=48000
SCRIPT=json.loads((ROOT/'work/voiceover-script.json').read_text())
RNG=np.random.default_rng(6240)

def run_audio(args,signal=None):
 input_args=['-f','f32le','-ar',str(SR),'-ac','1','-i','pipe:0'] if signal is not None else args[:2]
 options=args if signal is not None else args[2:]
 command=['ffmpeg','-hide_banner','-loglevel','error',*input_args,*options,'-ar',str(SR),'-ac','1','-f','f32le','pipe:1']
 return np.frombuffer(subprocess.check_output(command,input=signal.astype('<f4').tobytes() if signal is not None else None),dtype='<f4').copy()

def wav(path,signal):
 data=np.asarray(signal)
 channels=1 if data.ndim==1 else data.shape[1]
 assert np.isfinite(data).all() and abs(data).max()<1,('Clipping or invalid samples',path)
 with wave.open(str(path),'wb') as w:
  w.setnchannels(channels);w.setsampwidth(2);w.setframerate(SR)
  w.writeframes(np.rint(data*32767).astype('<i2').tobytes())

def fade(signal,attack=.008,release=.025):
 signal=signal.copy();a=min(len(signal),int(attack*SR));r=min(len(signal),int(release*SR))
 signal[:a]*=np.linspace(0,1,a);signal[-r:]*=np.linspace(1,0,r)
 return signal

def trim(signal):
 # Clip only leading/trailing silence. Keep phrase-internal pauses intact.
 idx=np.flatnonzero(np.abs(signal)>.002)
 assert len(idx),'Speech file has no audible content'
 return signal[max(0,idx[0]-int(.045*SR)):min(len(signal),idx[-1]+int(.09*SR))]

def fit(signal,available):
 ratio=max(1,len(signal)/SR/available)
 if ratio>1.18:raise ValueError(f'Speech needs wording revision: speed {ratio:.3f}')
 if ratio>1:signal=run_audio(['-af',f'atempo={ratio:.6f}'],signal)
 return signal,ratio

def add(stem,signal,start,pan=0):
 offset=round(start*SR);end=min(len(stem),offset+len(signal));n=end-offset
 if n<=0:return
 if signal.ndim==1:
  if stem.ndim==1:stem[offset:end]+=signal[:n]
  else:
   stem[offset:end,0]+=signal[:n]*math.sqrt((1-pan)/2)
   stem[offset:end,1]+=signal[:n]*math.sqrt((1+pan)/2)
 else:stem[offset:end]+=signal[:n]

def tone(midi,seconds,kind='bell'):
 t=np.arange(round(seconds*SR))/SR;hz=440*2**((midi-69)/12)
 if kind=='bell':
  y=(np.sin(2*np.pi*hz*t)+.2*np.sin(2*np.pi*2*hz*t)*np.exp(-9*t)+.05*np.sin(2*np.pi*3*hz*t))*np.exp(-5*t)
 elif kind=='pad':
  y=(np.sin(2*np.pi*hz*t)+.22*np.sin(2*np.pi*(hz*1.002)*t)+.07*np.sin(2*np.pi*2*hz*t))*.5
  y*=np.minimum(t/.4,1)*np.minimum((seconds-t)/.5,1)
 else:
  y=(np.sin(2*np.pi*hz*t)+.18*np.sin(2*np.pi*2*hz*t))*np.exp(-2.2*t)
 return fade(y)

def music(seconds):
 stem=np.zeros((round(seconds*SR),2));beat=.5
 # Original F# minor / D / A / E progression. No recordings or third-party song.
 chords=[(54,57,61,64),(50,54,57,61),(57,61,64,68),(52,56,59,63)]
 arp=[0,2,1,3,2,1,3,1]
 for bar_start in np.arange(0,seconds,4):
  chord=chords[int(bar_start//4)%len(chords)]
  for j,note in enumerate(chord):add(stem,tone(note,4.4,'pad')*.018,float(bar_start),pan=(j-1.5)*.35)
 for i,start in enumerate(np.arange(0,seconds,.25)):
  chord=chords[int(start//4)%len(chords)]
  gain=.018 if start<6 else .026
  if 38<=start<40:gain*=.65
  add(stem,tone(chord[arp[i%8]]+12,.85)*gain,float(start),pan=(-.55 if i%2 else .55))
 for i,start in enumerate(np.arange(0,seconds,beat)):
  chord=chords[int(start//4)%len(chords)]
  add(stem,tone(chord[0]-24,.42,'bass')*.05,float(start),pan=0)
  if start>=3 and not 38<=start<40:
   t=np.arange(round(.24*SR))/SR
   phase=2*np.pi*(46*t+60*.025*(1-np.exp(-t/.025)))
   kick=fade(np.sin(phase)*np.exp(-20*t))*.10
   add(stem,kick,float(start))
   if i%2:
    t=np.arange(round(.15*SR))/SR;n=RNG.normal(0,1,len(t));n=np.r_[0,np.diff(n)]
    clap=fade(n*np.exp(-35*t))*.009
    add(stem,clap,float(start),pan=.05)
 for i,start in enumerate(np.arange(6,seconds,.25)):
  t=np.arange(round(.07*SR))/SR;n=RNG.normal(0,1,len(t));n=np.r_[0,np.diff(n)]
  add(stem,fade(n*np.exp(-85*t))*(.003 if i%2 else .005),float(start),pan=.4 if i%2 else -.3)
 # A short original resolving chord for the product end-card.
 at=seconds-4
 for j,n in enumerate([54,57,61,66]):add(stem,tone(n+12,3.6)*.026,at+j*.06,pan=(j-1.5)*.3)
 env=np.minimum(np.arange(len(stem))/SR/.6,1)*np.minimum((len(stem)-1-np.arange(len(stem)))/SR/1.35,1)
 return stem*env[:,None]

def effects(seconds,transitions):
 stem=np.zeros((round(seconds*SR),2))
 for i,at in enumerate(transitions):
  if i%2==0:
   t=np.arange(round(.25*SR))/SR;n=RNG.normal(0,1,len(t))
   smooth=np.convolve(n,np.ones(19)/19,'same')
   whoosh=fade(smooth*np.sin(np.pi*np.linspace(0,1,len(t)))**2)*.022
   add(stem,whoosh,max(0,at-.09),pan=-.25 if i%4==0 else .25)
  add(stem,tone(78 if i%2 else 73,.20)*.012,at+.04,pan=.15)
 return stem

def encode(src,dest):
 subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(src),'-c:a','libmp3lame','-b:a','192k',str(dest)],check=True)

segments={};records=[]
for s in SCRIPT['segments']:
 raw=run_audio(['-i',str(ROOT/f"work/audio-raw/voice-{s['id']}.mp3")])
 speech=trim(raw)
 speech,ratio=fit(speech,s['latest_end']-s['start']-.12)
 speech=run_audio(['-af','loudnorm=I=-18:TP=-3:LRA=7'],speech)
 speech=fade(speech)
 assert s['start']+len(speech)/SR<=s['latest_end']-.08,(s['id'],'speech exceeds slot')
 segments[s['id']]=speech
 wav(OUT/f"voice-{s['id']}.wav",speech)
 records.append({**s,'file':f"audio/voice-{s['id']}.wav",'raw_duration':len(raw)/SR,'duration':len(speech)/SR,'speed_adjustment':ratio,'end':s['start']+len(speech)/SR})

mix_records=[]
for name,seconds,cues,transitions in [
 ('main',62,[{'source':s['id'],**s} for s in SCRIPT['segments']],[3,6,9,13,16,18,20,23,27,31,34,38,40,45,49,54,57]),
 ('sample',15,SCRIPT['sample'],[3,7,10,12])]:
 voice=np.zeros(round(seconds*SR));slots=[]
 for c in cues:
  speech,ratio=fit(segments[c['source']],c['latest_end']-c['start']-.12)
  speech=fade(speech)
  add(voice,speech,c['start'])
  end=c['start']+len(speech)/SR
  slots.append({'source':c['source'],'start':c['start'],'end':end,'latest_end':c['latest_end'],'speed_adjustment':ratio})
  assert end<c['latest_end']
 bed=music(seconds)*2.6;sfx=effects(seconds,transitions)*3.8
 clock=np.arange(len(voice))/SR
 duck=np.ones(len(voice))
 for slot in slots:
  attack=np.clip((clock-(slot['start']-.14))/.11,0,1)
  release=1-np.clip((clock-slot['end'])/.30,0,1)
  duck=np.minimum(duck,1-.65*np.minimum(attack,release))
 bed*=duck[:,None]
 v=np.column_stack([voice,voice])
 mix=v+bed+sfx
 peak=float(np.max(np.abs(mix)));gain=min(1,.80/max(peak,1e-9))
 # One gain for every stem makes Studio summation match this checked mix.
 for stem_name,signal in [('voice',v),('music',bed),('sfx',sfx),('mix',mix)]:
  path=CHECK/f'{name}-{stem_name}.wav';wav(path,signal*gain)
  encode(path,OUT/f'{name}-{stem_name}.mp3')
 mix_records.append({'name':name,'seconds':seconds,'sample_rate':SR,'sample_frames':len(voice),'voice_segments':slots,'master_gain':gain,'peak_dbfs':20*math.log10(float(np.max(np.abs(mix*gain)))+1e-15),'music_bpm':120,'music_original':True,'audio_only_no_video_export':True})

(ROOT/'work/audio-manifest.json').write_text(json.dumps({'speech_engine':'edge-tts / Microsoft Edge online TTS','voice':SCRIPT['voice'],'rate':SCRIPT['rate'],'segments':records,'mixes':mix_records,'assets':[{'file':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(OUT.glob('*'))]},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'speech_segments':len(records),'main_seconds':62,'sample_seconds':15,'mixes':[{'name':m['name'],'peak_dbfs':round(m['peak_dbfs'],2)} for m in mix_records]},ensure_ascii=False))
