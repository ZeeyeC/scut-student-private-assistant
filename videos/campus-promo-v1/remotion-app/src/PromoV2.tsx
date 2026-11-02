import {Video} from '@remotion/media';
import {TransitionSeries, linearTiming} from '@remotion/transitions';
import {wipe} from '@remotion/transitions/wipe';
import {slide} from '@remotion/transitions/slide';
import {AbsoluteFill, CanvasImage, Easing, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import './Composition';
import {MainPromoAudio, SamplePromoAudio} from './PromoAudio';

const ink='#111329', violet='#7665f5', paper='#f3f5fa';
const motion={extrapolateLeft:'clamp',extrapolateRight:'clamp',easing:Easing.bezier(.16,1,.3,1)} as const;
const film=(name:string)=>staticFile('footage/'+name+'.mp4');
const Base=({dark=false,children}:{dark?:boolean;children:React.ReactNode})=><AbsoluteFill style={{background:dark?ink:paper,color:dark?'#fff':ink,fontFamily:'Promo, sans-serif',overflow:'hidden'}}>{children}</AbsoluteFill>;
const Mark=({dark=false}:{dark?:boolean})=><div style={{position:'absolute',left:72,top:48,fontSize:25,fontWeight:700,letterSpacing:5,color:dark?'#fff':ink,zIndex:10}}>课间<span style={{display:'inline-block',width:7,height:7,background:violet,borderRadius:5,marginLeft:12}}/></div>;
const Note=({dark=false}:{dark?:boolean})=><div style={{position:'absolute',bottom:35,left:72,fontSize:18,color:dark?'#9a9cb8':'#8a8ea4',zIndex:10}}>虚构演示 · 操作片段已剪辑</div>;

const Word=({children,delay=0,style}:{children:React.ReactNode;delay?:number;style?:React.CSSProperties})=>{
 const f=useCurrentFrame();const {fps}=useVideoConfig();
 return <div style={{overflow:'hidden',...style}}><div style={{translate:interpolate(f,[delay,delay+.45*fps],['0px 115%','0px 0%'],motion),opacity:interpolate(f,[delay,delay+.18*fps],[0,1],motion)}}>{children}</div></div>;
};
const Panel=({file,style,delay=0,rate=1,angle=0}:{file:string;style:React.CSSProperties;delay?:number;rate?:number;angle?:number})=>{
 const f=useCurrentFrame();const {fps}=useVideoConfig();
 return <div style={{position:'absolute',borderRadius:22,overflow:'hidden',background:'#fff',boxShadow:'0 30px 90px #080d2a26',...style,opacity:interpolate(f,[delay,delay+.2*fps],[0,1],motion),translate:interpolate(f,[delay,delay+.65*fps],['90px 55px','0px 0px'],motion),transform:`perspective(1700px) rotateY(${interpolate(f,[delay,delay+.8*fps],[angle,0],motion)}deg)`}}><Video src={film(file)} muted playbackRate={rate} style={{width:'100%',height:'100%'}} objectFit="contain"/></div>;
};

const Hook=()=>{
 const f=useCurrentFrame();const {fps}=useVideoConfig();
 return <Base dark>
  <div style={{position:'absolute',left:800,top:-500,width:1500,height:1500,borderRadius:'50%',background:'radial-gradient(circle,#6658db65,transparent 66%)',scale:interpolate(f,[0,3*fps],[.8,1.3],motion)}}/>
  <Word style={{position:'absolute',left:110,top:170,fontSize:140,fontWeight:700,letterSpacing:3}}>课表。</Word>
  <Word delay={.2*fps} style={{position:'absolute',left:110,top:355,fontSize:140,fontWeight:700,letterSpacing:3}}>作业。</Word>
  <Word delay={.4*fps} style={{position:'absolute',left:110,top:540,fontSize:140,fontWeight:700,letterSpacing:3,color:'#b9aeff'}}>资料。</Word>
  <div style={{position:'absolute',left:1040,top:170,width:520,height:650,background:'#fff',borderRadius:20,overflow:'hidden',rotate:interpolate(f,[0,2.8*fps],['13deg','-5deg'],motion),translate:interpolate(f,[0,.8*fps],['500px 120px','0px 0px'],motion),boxShadow:'0 60px 120px #0007'}}><CanvasImage src={staticFile('materials/作业通知.png')} style={{width:'100%',height:'100%',objectFit:'cover'}}/></div>
  <div style={{position:'absolute',left:800,top:750,width:730,height:160,background:violet,borderRadius:22,padding:'20px 40px',boxSizing:'border-box',fontSize:62,fontWeight:700,rotate:'-6deg',translate:interpolate(f,[.8*fps,1.3*fps],['900px 0px','0px 0px'],motion)}}>接进同一个流程。</div>
 </Base>;
};
const BrandReveal=()=>{
 const f=useCurrentFrame();const {fps}=useVideoConfig();
 return <Base><Mark/>
  <div style={{position:'absolute',left:-120,top:600,fontSize:310,fontWeight:700,letterSpacing:12,color:'#e0def9',translate:interpolate(f,[0,3*fps],['-90px 0px','35px 0px'],motion)}}>课间</div>
  <Word style={{position:'absolute',left:105,top:190,fontSize:114,fontWeight:700,zIndex:2}}>安排清楚。</Word>
  <Panel file="today-results" delay={.15*fps} angle={-12} style={{left:470,top:365,width:1370,height:550,rotate:'-3deg'}}/>
  <div style={{position:'absolute',right:120,top:180,width:190,height:190,borderRadius:'50%',border:'2px solid #8b7ff0',scale:interpolate(f,[0,2.7*fps],[.6,1.15],motion),opacity:.5}}/>
 </Base>;
};
const UploadSplit=()=>{
 const f=useCurrentFrame();const {fps}=useVideoConfig();
 return <Base dark><Mark dark/>
  <div style={{position:'absolute',left:120,top:160,width:620,height:780,borderRadius:24,overflow:'hidden',background:'#fff',rotate:interpolate(f,[0,.7*fps],['-12deg','-4deg'],motion),translate:interpolate(f,[0,.6*fps],['-500px 100px','0px 0px'],motion)}}>
   <CanvasImage src={staticFile('materials/作业通知.png')} style={{width:'100%',height:'100%',objectFit:'contain'}}/>
   <div style={{position:'absolute',left:25,right:25,top:interpolate(f,[.5*fps,2.5*fps],[80,700],motion),height:3,background:'#b2a5ff',boxShadow:'0 0 22px #897bff'}}/>
  </div>
  <Word delay={.15*fps} style={{position:'absolute',left:900,top:280,fontSize:112,fontWeight:700,lineHeight:1.5}}>一张截图。</Word>
  <Word delay={.4*fps} style={{position:'absolute',left:900,top:445,fontSize:112,fontWeight:700,color:'#b4a8ff'}}>变成待办。</Word>
  <div style={{position:'absolute',left:910,top:690,width:650,height:5,background:'#3d365f',overflow:'hidden'}}><div style={{height:'100%',width:interpolate(f,[.8*fps,2.6*fps],[0,650],motion),background:violet}}/></div>
  <Note dark/>
 </Base>;
};
const DraftFocus=()=>{
 const f=useCurrentFrame();const {fps}=useVideoConfig();
 return <Base><Mark/>
  <div style={{position:'absolute',right:90,top:50,fontSize:32,color:'#777c95'}}>识别结果</div>
  <div style={{position:'absolute',left:45,top:260,fontSize:330,fontWeight:700,color:'#e7e3ff',translate:interpolate(f,[0,.55*fps],['-240px 0px','0px 0px'],motion)}}>2</div>
  <div style={{position:'absolute',left:250,top:175,width:1590,height:710,overflow:'hidden',borderRadius:24,background:'#fff',scale:interpolate(f,[0,4*fps],[.94,1.02],motion)}}><Video src={film('image-draft')} muted style={{width:'100%',height:'100%'}} objectFit="contain"/></div>
  <Word delay={.25*fps} style={{position:'absolute',left:100,top:900,fontSize:53,fontWeight:700}}>先核对，再保存。</Word>
 </Base>;
};
const DateFocus=()=>{
 const f=useCurrentFrame();const {fps}=useVideoConfig();
 return <Base dark><Mark dark/>
  <Word style={{position:'absolute',right:110,top:130,fontSize:92,fontWeight:700,textAlign:'right',lineHeight:1.4}}>日期，<br/><span style={{color:'#c2b9ff'}}>可以之后填。</span></Word>
  <Panel file="image-deadline" angle={9} style={{left:90,top:410,width:1530,height:560,rotate:interpolate(f,[0,2.6*fps],['-4deg','-1deg'],motion)}}/>
  <Note dark/>
 </Base>;
};
const TaskLaunch=()=> <Base><Mark/>
 <Panel file="task-results" angle={-10} style={{left:80,top:300,width:1190,height:540}}/>
 <Word style={{position:'absolute',left:1350,top:310,fontSize:105,fontWeight:700,lineHeight:1.4}}>进入<br/><span style={{color:violet}}>待办。</span></Word>
 <Note/>
</Base>;
const ScheduleOpener=()=>{
 const f=useCurrentFrame();const {fps}=useVideoConfig();
 return <Base dark>
  <div style={{position:'absolute',right:-280,top:-500,width:1300,height:1300,borderRadius:'50%',border:'100px solid #242446',rotate:interpolate(f,[0,2*fps],['-30deg','90deg'],motion)}}/>
  <Word style={{position:'absolute',left:140,top:300,fontSize:126,fontWeight:700}}>你的课程。</Word>
  <Word delay={.25*fps} style={{position:'absolute',left:140,top:480,fontSize:126,fontWeight:700,color:'#b5a9ff'}}>安排会避让。</Word>
 </Base>;
};
const CalendarSweep=()=>{
 const f=useCurrentFrame();const {fps}=useVideoConfig();
 return <Base><Mark/>
  <Word style={{position:'absolute',left:100,top:340,fontSize:95,fontWeight:700,lineHeight:1.5}}>已有课表，<br/>一起考虑。</Word>
  <Panel file="calendar-context" rate={.9} angle={-12} style={{left:780,top:90,width:1050,height:900,rotate:interpolate(f,[0,3*fps],['3deg','-1deg'],motion)}}/>
 </Base>;
};
const PlanSplit=()=>{
 const f=useCurrentFrame();const {fps}=useVideoConfig();
 return <Base dark><Mark dark/>
  <div style={{position:'absolute',left:100,top:190,fontSize:35,color:'#b5a9ff'}}>今晚的安排草稿</div>
  <Word style={{position:'absolute',left:100,top:275,fontSize:130,fontWeight:700}}>19:10</Word>
  <Word delay={.22*fps} style={{position:'absolute',left:100,top:450,fontSize:130,fontWeight:700,color:'#b5a9ff'}}>19:35</Word>
  <div style={{position:'absolute',left:110,top:660,fontSize:38,color:'#b7b9d2'}}>两项作业，各 25 分钟</div>
  <Panel file="planning-draft" angle={-9} style={{left:700,top:250,width:1150,height:600,scale:interpolate(f,[0,4*fps],[.94,1.02],motion)}}/>
  <Note dark/>
 </Base>;
};
const TodayDive=()=>{
 const f=useCurrentFrame();const {fps}=useVideoConfig();
 return <Base><Mark/>
  <div style={{position:'absolute',left:0,top:130,width:1920,height:780,scale:interpolate(f,[0,1*fps,4*fps],[.94,1,1.04],motion)}}><Video src={film('today-results')} muted style={{width:'100%',height:'100%'}} objectFit="contain"/></div>
  <Word style={{position:'absolute',left:100,top:930,fontSize:55,fontWeight:700}}>确认之后，才进日程。</Word>
 </Base>;
};
const FileShelf=()=>{
 const f=useCurrentFrame();const {fps}=useVideoConfig();
 return <Base><Mark/>
  <Word style={{position:'absolute',left:100,top:190,fontSize:108,fontWeight:700,lineHeight:1.5}}>按课程，<br/><span style={{color:violet}}>收好。</span></Word>
  <div style={{position:'absolute',right:100,top:570,width:330,height:465,borderRadius:12,overflow:'hidden',background:'#fff',rotate:interpolate(f,[0,3*fps],['12deg','6deg'],motion),boxShadow:'0 22px 80px #17214d23'}}><CanvasImage src={staticFile('materials/lecture-preview.png')} style={{width:'100%',height:'100%',objectFit:'contain'}}/></div>
  <Panel file="library-list" delay={.15*fps} angle={-15} style={{left:700,top:165,width:1100,height:530,rotate:'-2deg'}}/>
  <Note/>
 </Base>;
};
const Answer=()=>{
 const f=useCurrentFrame();const {fps}=useVideoConfig();
 return <Base><Mark/>
  <div style={{position:'absolute',left:90,top:200,fontSize:300,fontWeight:700,color:violet,scale:interpolate(f,[0,.5*fps],[1.5,1],motion),opacity:interpolate(f,[0,.2*fps],[0,1],motion)}}>10</div>
  <Word delay={.25*fps} style={{position:'absolute',left:110,top:650,fontSize:67,fontWeight:700,lineHeight:1.5}}>问答，<br/>有出处。</Word>
  <Panel file="knowledge-answer" delay={.15*fps} angle={-8} style={{left:690,top:240,width:1160,height:570}}/>
  <Note/>
 </Base>;
};
const MemoryOpener=()=>{
 const f=useCurrentFrame();const {fps}=useVideoConfig();
 return <Base dark>
  <div style={{position:'absolute',left:1160,top:170,width:640,height:640,border:'2px solid #6558bd',borderRadius:'50%',scale:interpolate(f,[0,2*fps],[.7,1.15],motion)}}/>
  <div style={{position:'absolute',left:110,top:180,fontSize:360,fontWeight:700,letterSpacing:-15,color:'#b8adff'}}>25<span style={{fontSize:75,letterSpacing:4,marginLeft:30}}>MIN</span></div>
  <Word delay={.2*fps} style={{position:'absolute',left:130,top:720,fontSize:68,fontWeight:700}}>记住的，由你定。</Word>
 </Base>;
};
const MemoryConfirm=()=> <Base dark><Mark dark/>
 <Word style={{position:'absolute',left:100,top:300,fontSize:90,fontWeight:700,lineHeight:1.6}}>先确认。<br/><span style={{color:'#b9aeff'}}>再记住。</span></Word>
 <Panel file="memory-confirm" rate={1.3} angle={-13} style={{left:650,top:195,width:1190,height:710}}/>
 <Note dark/>
</Base>;
const Recall=()=>{
 const f=useCurrentFrame();const {fps}=useVideoConfig();
 return <Base><Mark/>
  <div style={{position:'absolute',right:90,top:550,fontSize:300,fontWeight:700,color:'#ded8ff',translate:interpolate(f,[0,3.8*fps],['120px 0px','0px 0px'],motion)}}>25</div>
  <Panel file="memory-recall" rate={.9} angle={5} style={{left:100,top:180,width:1690,height:460}}/>
  <Word delay={.2*fps} style={{position:'absolute',left:110,top:760,fontSize:78,fontWeight:700,lineHeight:1.5}}>换个对话，<br/>继续记得。</Word>
 </Base>;
};
const Desktop=()=>{
 const f=useCurrentFrame();const {fps}=useVideoConfig();
 return <Base><Mark/>
  <Word style={{position:'absolute',left:100,top:340,fontSize:86,fontWeight:700,lineHeight:1.6}}>关上窗口，<br/>待办还在。</Word>
  <div style={{position:'absolute',left:105,top:650,height:7,width:interpolate(f,[.4*fps,1*fps],[0,520],motion),background:violet,borderRadius:8}}/>
  <div style={{position:'absolute',left:930,top:100,width:900,height:850,scale:interpolate(f,[0,5*fps],[.88,1],motion)}}><Video src={film('pet-result')} muted playbackRate={.9} style={{width:'100%',height:'100%'}} objectFit="contain"/></div>
  <Note/>
 </Base>;
};
const Montage=()=>{
 const f=useCurrentFrame();const {fps}=useVideoConfig();
 return <Base dark><Mark dark/>
  <Word style={{position:'absolute',left:100,top:140,fontSize:100,fontWeight:700}}>从截图，到安排。</Word>
  <Panel file="image-draft" angle={-15} style={{left:90,top:400,width:760,height:470,rotate:interpolate(f,[0,3*fps],['-8deg','-3deg'],motion)}}/>
  <Panel file="today-results" delay={.2*fps} angle={10} style={{left:740,top:340,width:950,height:540,rotate:interpolate(f,[0,3*fps],['7deg','2deg'],motion)}}/>
 </Base>;
};
const Finale=()=>{
 const f=useCurrentFrame();const {fps}=useVideoConfig();
 return <Base dark>
  <div style={{position:'absolute',left:210,top:-460,width:1500,height:1500,borderRadius:'50%',background:'radial-gradient(circle,#5447a94d,transparent 65%)'}}/>
  <div style={{position:'absolute',width:'100%',top:265,textAlign:'center',fontSize:250,fontWeight:700,letterSpacing:20,scale:interpolate(f,[0,.8*fps],[1.5,1],motion),opacity:interpolate(f,[0,.3*fps],[0,1],motion)}}>课间</div>
  <Word delay={.35*fps} style={{position:'absolute',width:'100%',top:640,textAlign:'center',fontSize:49,color:'#c0bedb',letterSpacing:5}}>让学习安排更清楚</Word>
  <div style={{position:'absolute',left:665,top:760,height:5,width:interpolate(f,[.55*fps,1.2*fps],[0,590],motion),background:violet,borderRadius:8}}/>
  <div style={{position:'absolute',width:'100%',bottom:65,textAlign:'center',fontSize:20,color:'#9294ad'}}>视频中的课程、作业与资料均为虚构演示样例</div>
 </Base>;
};

// Each sequence includes 8 extra frames; each transition overlaps those frames.
// Core durations total 62 seconds, with no shortening or uncounted overlap.
export const CampusPromoV2=()=>{
 const {fps}=useVideoConfig();
 return <><MainPromoAudio/><TransitionSeries>
  <TransitionSeries.Sequence name="01 快速大字开场" durationInFrames={3*fps+8}><Hook/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={wipe({direction:'from-left'})} timing={linearTiming({durationInFrames:8})}/>
  <TransitionSeries.Sequence name="02 品牌与完整窗口" durationInFrames={3*fps+8}><BrandReveal/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={slide({direction:'from-bottom'})} timing={linearTiming({durationInFrames:8})}/>
  <TransitionSeries.Sequence name="03 原图左右分屏" durationInFrames={3*fps+8}><UploadSplit/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={wipe({direction:'from-right'})} timing={linearTiming({durationInFrames:8})}/>
  <TransitionSeries.Sequence name="04 全屏草稿近景" durationInFrames={4*fps+8}><DraftFocus/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={slide({direction:'from-left'})} timing={linearTiming({durationInFrames:8})}/>
  <TransitionSeries.Sequence name="05 日期错位构图" durationInFrames={3*fps+8}><DateFocus/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={wipe({direction:'from-top'})} timing={linearTiming({durationInFrames:8})}/>
  <TransitionSeries.Sequence name="06 待办落地" durationInFrames={2*fps+8}><TaskLaunch/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={wipe({direction:'from-left'})} timing={linearTiming({durationInFrames:8})}/>
  <TransitionSeries.Sequence name="07 课程节奏卡" durationInFrames={2*fps+8}><ScheduleOpener/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={slide({direction:'from-right'})} timing={linearTiming({durationInFrames:8})}/>
  <TransitionSeries.Sequence name="08 课程窗口推镜" durationInFrames={3*fps+8}><CalendarSweep/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={wipe({direction:'from-bottom'})} timing={linearTiming({durationInFrames:8})}/>
  <TransitionSeries.Sequence name="09 时间与安排分屏" durationInFrames={4*fps+8}><PlanSplit/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={slide({direction:'from-top'})} timing={linearTiming({durationInFrames:8})}/>
  <TransitionSeries.Sequence name="10 全幅今日安排" durationInFrames={4*fps+8}><TodayDive/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={wipe({direction:'from-right'})} timing={linearTiming({durationInFrames:8})}/>
  <TransitionSeries.Sequence name="11 文件层次与课程分类" durationInFrames={3*fps+8}><FileShelf/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={slide({direction:'from-left'})} timing={linearTiming({durationInFrames:8})}/>
  <TransitionSeries.Sequence name="12 答案与原文来源" durationInFrames={4*fps+8}><Answer/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={wipe({direction:'from-left'})} timing={linearTiming({durationInFrames:8})}/>
  <TransitionSeries.Sequence name="13 记忆数字节奏卡" durationInFrames={2*fps+8}><MemoryOpener/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={slide({direction:'from-bottom'})} timing={linearTiming({durationInFrames:8})}/>
  <TransitionSeries.Sequence name="14 人工确认大近景" durationInFrames={5*fps+8}><MemoryConfirm/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={wipe({direction:'from-right'})} timing={linearTiming({durationInFrames:8})}/>
  <TransitionSeries.Sequence name="15 新会话召回" durationInFrames={4*fps+8}><Recall/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={slide({direction:'from-right'})} timing={linearTiming({durationInFrames:8})}/>
  <TransitionSeries.Sequence name="16 桌宠留在桌面" durationInFrames={5*fps+8}><Desktop/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={wipe({direction:'from-bottom'})} timing={linearTiming({durationInFrames:8})}/>
  <TransitionSeries.Sequence name="17 卡片交叠蒙太奇" durationInFrames={3*fps+8}><Montage/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={wipe({direction:'from-left'})} timing={linearTiming({durationInFrames:8})}/>
  <TransitionSeries.Sequence name="18 品牌收束" durationInFrames={5*fps}><Finale/></TransitionSeries.Sequence>
 </TransitionSeries></>;
};

export const HomeworkPreviewV2=()=>{
 const {fps}=useVideoConfig();
 return <><SamplePromoAudio/><TransitionSeries>
  <TransitionSeries.Sequence name="原图进入" durationInFrames={3*fps+8}><UploadSplit/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={wipe({direction:'from-left'})} timing={linearTiming({durationInFrames:8})}/>
  <TransitionSeries.Sequence name="草稿全幅近景" durationInFrames={4*fps+8}><DraftFocus/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={slide({direction:'from-bottom'})} timing={linearTiming({durationInFrames:8})}/>
  <TransitionSeries.Sequence name="日期错位卡片" durationInFrames={3*fps+8}><DateFocus/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={wipe({direction:'from-right'})} timing={linearTiming({durationInFrames:8})}/>
  <TransitionSeries.Sequence name="待办结果" durationInFrames={2*fps+8}><TaskLaunch/></TransitionSeries.Sequence>
  <TransitionSeries.Transition presentation={slide({direction:'from-left'})} timing={linearTiming({durationInFrames:8})}/>
  <TransitionSeries.Sequence name="课间" durationInFrames={3*fps}><Finale/></TransitionSeries.Sequence>
 </TransitionSeries></>;
};
