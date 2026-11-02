import {Audio} from '@remotion/media';
import {staticFile, Track, useVideoConfig} from 'remotion';

// Ducking, fades and headroom are authored in build-audio.py; keep stems at unity
// so Studio reproduces the checked mix, with independently editable tracks.
export const MainPromoAudio=()=>{
 const {fps}=useVideoConfig();
 return <>
  <Track name="中文旁白"><Audio name="晓晓 · 18句旁白" src={staticFile('audio/main-voice.mp3')} durationInFrames={62*fps}/></Track>
  <Track name="原创背景音乐"><Audio name="120 BPM · 旁白时降低音量" src={staticFile('audio/main-music.mp3')} durationInFrames={62*fps}/></Track>
  <Track name="转场与落点音效"><Audio name="原创轻量音效" src={staticFile('audio/main-sfx.mp3')} durationInFrames={62*fps}/></Track>
 </>;
};

export const SamplePromoAudio=()=>{
 const {fps}=useVideoConfig();
 return <>
  <Track name="样段中文旁白"><Audio name="作业整理 · 重新对齐的旁白" src={staticFile('audio/sample-voice.mp3')} durationInFrames={15*fps}/></Track>
  <Track name="样段背景音乐"><Audio name="15秒原创音乐" src={staticFile('audio/sample-music.mp3')} durationInFrames={15*fps}/></Track>
  <Track name="样段音效"><Audio name="样段转场落点" src={staticFile('audio/sample-sfx.mp3')} durationInFrames={15*fps}/></Track>
 </>;
};
