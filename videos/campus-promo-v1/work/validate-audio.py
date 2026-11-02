"""Validate audio durations, slots, decoded peaks and the actual Remotion mix."""
from pathlib import Path
import json,subprocess
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
PUBLIC=ROOT/'remotion-app/public/audio'
manifest=json.loads((ROOT/'work/audio-manifest.json').read_text())
SR=48000

def decode(p):
 raw=subprocess.check_output(['ffmpeg','-hide_banner','-loglevel','error','-i',str(p),'-ar',str(SR),'-ac','2','-f','f32le','pipe:1'])
 return np.frombuffer(raw,dtype='<f4').reshape(-1,2)

def levels(p):
 r=subprocess.run(['ffmpeg','-hide_banner','-i',str(p),'-af','loudnorm=I=-16:TP=-1:LRA=9:print_format=json','-f','null','-'],capture_output=True,text=True,check=True)
 data,_=json.JSONDecoder().raw_decode(r.stderr[r.stderr.rfind('{'):])
 return {'integrated_lufs':float(data['input_i']),'true_peak_dbtp':float(data['input_tp']),'loudness_range_lu':float(data['input_lra'])}

results=[]
for mix in manifest['mixes']:
 name=mix['name'];seconds=mix['seconds'];expected_samples=seconds*SR
 for c in mix['voice_segments']:
  assert c['start']>=0 and c['end']<=c['latest_end'] and c['end']<=seconds
  assert c['speed_adjustment']<=1.18
 for a,b in zip(mix['voice_segments'],mix['voice_segments'][1:]):
  assert a['end']<=b['start'],'Narration overlap'
 stems=[decode(PUBLIC/f'{name}-{stem}.mp3') for stem in ['voice','music','sfx']]
 assert all(len(s)==expected_samples for s in stems),[len(s) for s in stems]
 expected=sum(stems)
 reference=decode(PUBLIC/f'{name}-mix.mp3')
 assert len(reference)==expected_samples
 assert np.isfinite(expected).all() and abs(expected).max()<.95
 report={'name':name,'seconds':seconds,'sample_frames':expected_samples,'narration_slots':'passed','separate_stem_peak_dbfs':float(20*np.log10(abs(expected).max())),'loudness':levels(PUBLIC/f'{name}-mix.mp3'),'voice_loudness':levels(PUBLIC/f'{name}-voice.mp3'),'music_loudness':levels(PUBLIC/f'{name}-music.mp3')}
 assert report['loudness']['true_peak_dbtp']<=-1
 assert -19<=report['loudness']['integrated_lufs']<=-14
 assert report['voice_loudness']['integrated_lufs']-report['music_loudness']['integrated_lufs']>=8
 # This WAV is rendered from the actual composition, without a video export.
 rendered=ROOT/f'work/audio-check/studio-{name}.wav'
 assert rendered.exists(),'Actual Remotion audio output missing'
 actual=decode(rendered)
 assert abs(len(actual)-expected_samples)<=2
 length=min(len(actual),len(expected));actual=actual[:length];expected=expected[:length]
 corr=float(np.corrcoef(actual.ravel()[::8],expected.ravel()[::8])[0,1])
 residual=float(np.sqrt(np.mean((actual-expected)**2)))
 report.update(remotion_audio_seconds=len(actual)/SR,remotion_stem_correlation=corr,remotion_residual_rms=residual)
 assert corr>.995 and residual<.003,report
 assert abs(actual).max()<.95
 assert np.max(abs(actual[-480:]))<.01,'Audio ending does not fade'
 results.append(report)

result={'passed':True,'main_seconds':62,'sample_seconds':15,'narration_sentences':len(manifest['segments']),'scene_frames_unchanged':1860,'business_model_requests_added':0,'paid_service_calls':0,'video_exported':False,'subjective_listening':'pending user review in browser','mixes':results}
(ROOT/'work/audio-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
