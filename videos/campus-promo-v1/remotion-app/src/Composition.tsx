import {AbsoluteFill, CanvasImage, Easing, interpolate, Sequence, staticFile, Track, useCurrentFrame, useVideoConfig} from 'remotion';
import {loadFont} from '@remotion/fonts';

loadFont({family:'Promo',url:staticFile('fonts/Promo-Regular.woff2'),weight:'400'});
loadFont({family:'Promo',url:staticFile('fonts/Promo-Bold.woff2'),weight:'700'});
const theme={ink:'#282e42',muted:'#7d859c',accent:'#7475cf',bg:'#f3f5fa'};
const base:React.CSSProperties={fontFamily:'Promo, sans-serif',color:theme.ink,background:theme.bg};
const clamp={extrapolateLeft:'clamp',extrapolateRight:'clamp'} as const;
const Brand=()=> <div style={{position:'absolute',left:100,top:72,fontSize:32,fontWeight:700,letterSpacing:5}}>课间<span style={{fontWeight:400,color:theme.muted,fontSize:20,letterSpacing:2,marginLeft:20}}>让学习安排更清楚</span></div>;

const PaperCard=({title,detail,index}:{title:string;detail:string;index:number})=>{
 const frame=useCurrentFrame();const {fps}=useVideoConfig();
 return <div style={{width:360,height:236,border:'1px solid #e1e5f0',background:'#fff',borderRadius:24,padding:'38px 40px',boxSizing:'border-box',boxShadow:'0 18px 60px #59668d0b',opacity:interpolate(frame,[index*.16*fps,(index*.16+.6)*fps],[0,1],clamp),translate:interpolate(frame,[index*.16*fps,(index*.16+.8)*fps],[`0px ${40+index*16}px`,'0px 0px'],{...clamp,easing:Easing.bezier(.16,1,.3,1)})}}>
  <div style={{width:42,height:5,background:theme.accent,borderRadius:8,marginBottom:30,opacity:.45+index*.2}}/>
  <div style={{fontSize:38,fontWeight:700,marginBottom:15}}>{title}</div><div style={{fontSize:23,color:theme.muted}}>{detail}</div>
 </div>;
};
export const Intro=()=>{
 const frame=useCurrentFrame();const {fps}=useVideoConfig();
 return <AbsoluteFill style={base}><Brand/>
  <div style={{position:'absolute',top:245,width:'100%',textAlign:'center',fontSize:90,fontWeight:700,letterSpacing:1,opacity:interpolate(frame,[0,.7*fps],[0,1],clamp)}}>课表、作业、资料</div>
  <div style={{position:'absolute',top:405,width:'100%',textAlign:'center',fontSize:34,color:theme.muted,opacity:interpolate(frame,[.5*fps,1.1*fps],[0,1],clamp)}}>从分散的信息，到清楚的安排</div>
  <div style={{position:'absolute',left:392,top:555,display:'flex',gap:28}}>
   <PaperCard title="课表" detail="每周的课程" index={0}/>
   <PaperCard title="作业" detail="课后的待办" index={1}/>
   <PaperCard title="资料" detail="随时带着原文提问" index={2}/>
  </div>
 </AbsoluteFill>;
};
export const Outro=()=>{
 const frame=useCurrentFrame();const {fps}=useVideoConfig();
 return <AbsoluteFill style={{...base,justifyContent:'center',alignItems:'center'}}>
  <div style={{fontSize:150,fontWeight:700,letterSpacing:18,opacity:interpolate(frame,[0,.7*fps],[0,1],clamp),translate:interpolate(frame,[0,.9*fps],['0px 24px','0px 0px'],clamp)}}>课间</div>
  <div style={{fontSize:40,color:theme.muted,marginTop:38,letterSpacing:3}}>让学习安排更清楚</div>
  <div style={{position:'absolute',bottom:70,fontSize:20,color:'#9299aa'}}>视频中的课程、作业与资料均为虚构演示样例</div>
 </AbsoluteFill>;
};
// Original material review; this is not simulated App behavior.
const MaterialReview=()=> <AbsoluteFill style={base}>
 <Brand/><div style={{position:'absolute',left:120,top:255,width:720}}>
  <div style={{fontSize:24,color:theme.accent,letterSpacing:3}}>虚构素材预览</div>
  <h1 style={{fontSize:74,lineHeight:1.35,margin:'25px 0 35px'}}>从一张作业截图<br/>开始整理</h1>
  <div style={{fontSize:30,lineHeight:1.9,color:theme.muted}}>两门虚构课程，两项课后练习。<br/>明确日期与未定日期同时保留。</div>
  <div style={{fontSize:21,color:'#9299aa',marginTop:100}}>本页仅展示原创素材，真实操作画面待录制。</div>
 </div>
 <CanvasImage src={staticFile('materials/作业通知.png')} style={{position:'absolute',right:150,top:160,width:730,height:738,objectFit:'contain',borderRadius:25,boxShadow:'0 28px 80px #52618716'}}/>
 </AbsoluteFill>;
export const StylePreview=()=>{
 const {fps}=useVideoConfig();
 return <Track name="风格与虚构素材预览">
  <Sequence name="片头" durationInFrames={5*fps}><Intro/></Sequence>
  <Sequence name="原创作业截图" from={5*fps} durationInFrames={6*fps}><MaterialReview/></Sequence>
  <Sequence name="片尾" from={11*fps} durationInFrames={4*fps}><Outro/></Sequence>
 </Track>;
};
