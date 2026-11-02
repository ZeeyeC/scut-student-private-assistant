"""Inspect the exported MP4 against the approved composition and audio."""
from pathlib import Path
import hashlib,json,math,re,subprocess
import numpy as np
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
EXPORT=ROOT/'edit/export-v2'
MOVIE=EXPORT/'课间-宣传片-V2-1080p.mp4'
CHECK=ROOT/'work/export-check';CHECK.mkdir(exist_ok=True)
assert MOVIE.exists() and MOVIE.stat().st_size>100000
probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_streams','-show_format','-of','json',str(MOVIE)],text=True))
video=next(s for s in probe['streams'] if s['codec_type']=='video')
audio=next(s for s in probe['streams'] if s['codec_type']=='audio')
assert video['codec_name']=='h264' and video['width']==1920 and video['height']==1080
assert video['pix_fmt']=='yuv420p' and video['r_frame_rate']=='30/1'
assert int(video['nb_read_frames'])==1860
assert audio['codec_name']=='aac' and audio['channels']==2
assert abs(float(video['duration'])-62)<.001
assert abs(float(audio['duration'])-62)<.06
decode=subprocess.run(['ffmpeg','-hide_banner','-v','error','-i',str(MOVIE),'-f','null','-'],capture_output=True,text=True)
assert decode.returncode==0 and not decode.stderr.strip(),decode.stderr
black=subprocess.run(['ffmpeg','-hide_banner','-i',str(MOVIE),'-vf','blackdetect=d=0.05:pix_th=0.02:pic_th=0.98','-an','-f','null','-'],capture_output=True,text=True,check=True)
black_intervals=[v[v.index('black_start:'):] for v in black.stderr.splitlines() if 'black_start:' in v]
assert not black_intervals,black_intervals

def samples(path):
 raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-ar','48000','-ac','2','-f','f32le','pipe:1'])
 return np.frombuffer(raw,dtype='<f4').reshape(-1,2)
actual=samples(MOVIE);expected=samples(ROOT/'work/audio-check/studio-main.wav')
length=min(len(actual),len(expected));actual=actual[:length];expected=expected[:length]
correlation=float(np.corrcoef(actual.ravel()[::8],expected.ravel()[::8])[0,1])
assert correlation>.99,correlation
peak=float(20*np.log10(abs(actual).max()))
assert peak<-1

frame_results=[];thumbs=[]
for frame in [35,140,245,370,500,595,740,845,980,1090,1220,1370,1520,1670,1800,1859]:
 image=CHECK/f'frame-{frame:04}.png'
 subprocess.run(['ffmpeg','-y','-v','error','-ss',f'{frame/30:.9f}','-i',str(MOVIE),'-frames:v','1',str(image)],check=True)
 approved=ROOT/f'work/v2-qa/element-{frame:04}.png'
 a=np.asarray(Image.open(image).convert('RGB'),dtype=np.float32)
 b=np.asarray(Image.open(approved).convert('RGB'),dtype=np.float32)
 mse=float(np.mean((a-b)**2));psnr=99 if mse==0 else 10*math.log10(255**2/mse)
 assert psnr>24,(frame,psnr)
 frame_results.append({'frame':frame,'seconds':frame/30,'psnr_against_checked_preview_db':round(psnr,3)})
 im=Image.open(image).convert('RGB');im.thumbnail((480,270));ImageDraw.Draw(im).text((10,10),f'{frame/30:.2f}s',fill='#ff6262');thumbs.append(im)
sheet=Image.new('RGB',(1440,270*((len(thumbs)+2)//3)),'#cdd1df')
for i,im in enumerate(thumbs):sheet.paste(im,(i%3*480,i//3*270))
sheet.save(CHECK/'export-review.jpg',quality=92)
checksum=hashlib.sha256(MOVIE.read_bytes()).hexdigest()
(EXPORT/'SHA256.txt').write_text(checksum+'  '+MOVIE.name+'\n')
report={'passed':True,'composition':'CampusPromoV2','file':MOVIE.name,'bytes':MOVIE.stat().st_size,'sha256':checksum,'width':1920,'height':1080,'fps':30,'frames':1860,'seconds':62,'video_codec':'H.264','pixel_format':'yuv420p','audio_codec':'AAC','audio_channels':2,'full_decode':'passed','black_intervals':black_intervals,'audio_correlation_against_approved_mix':correlation,'decoded_audio_peak_dbfs':peak,'visual_frame_comparisons':frame_results,'subjective_preview':'user approved browser audiovisual preview before export','public_upload':False}
(EXPORT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['passed','bytes','seconds','fps','frames','sha256','audio_correlation_against_approved_mix']},ensure_ascii=False))
