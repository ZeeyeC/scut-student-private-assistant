import {Video} from '@remotion/media';
import {AbsoluteFill, CanvasImage, Easing, interpolate, Sequence, staticFile, Track, useCurrentFrame, useVideoConfig} from 'remotion';
import {Intro, Outro} from './Composition';

const background='#f3f5fa';
const Frame=({title,children,note='真实 App 录屏 · 虚构演示资料 · 等待已剪辑'}:{title:string;children:React.ReactNode;note?:string})=>{
 const f=useCurrentFrame();const {fps}=useVideoConfig();
 return <AbsoluteFill style={{background,color:'#282e42',fontFamily:'Promo, sans-serif'}}>
  <div style={{position:'absolute',left:120,top:62,fontSize:28,fontWeight:700,letterSpacing:5}}>课间</div>
  <div style={{position:'absolute',left:120,top:118,fontSize:60,fontWeight:700,letterSpacing:1,opacity:interpolate(f,[0,.3*fps],[0,1],{extrapolateRight:'clamp',easing:Easing.bezier(.16,1,.3,1)})}}>{title}</div>
  <div style={{position:'absolute',left:120,top:250,width:1680,height:700,borderRadius:20,overflow:'hidden',background:'#fff',border:'1px solid #e2e6f0',boxShadow:'0 20px 70px #53638b12'}}>{children}</div>
  <div style={{position:'absolute',left:120,bottom:54,fontSize:20,color:'#858da1'}}>{note}</div>
 </AbsoluteFill>;
};
const Shot=({file,title}:{file:string;title:string})=><Frame title={title}><Video src={staticFile('footage/'+file+'.mp4')} muted style={{width:'100%',height:'100%'}} objectFit="contain"/></Frame>;
const DesktopShot=({file,title}:{file:string;title:string})=><AbsoluteFill style={{background,color:'#282e42',fontFamily:'Promo, sans-serif'}}>
 <div style={{position:'absolute',left:120,top:62,fontSize:28,fontWeight:700,letterSpacing:5}}>课间</div>
 <div style={{position:'absolute',left:120,top:380,width:680,fontSize:66,lineHeight:1.5,fontWeight:700}}>{title}</div>
 <Video src={staticFile('footage/'+file+'.mp4')} muted style={{position:'absolute',left:920,top:120,width:880,height:840}} objectFit="contain"/>
 <div style={{position:'absolute',left:120,bottom:54,fontSize:20,color:'#858da1'}}>真实桌宠窗口 · 虚构演示资料</div>
</AbsoluteFill>;
const Lecture=()=> <Frame title="带着原文，向助手提问" note="原创虚构讲义 · 第 1 页">
 <div style={{position:'absolute',left:90,top:175,fontSize:52,fontWeight:700,lineHeight:1.6}}>微积分<br/><span style={{fontWeight:400,color:'#7d859c',fontSize:36}}>导数应用练习</span></div>
 <CanvasImage src={staticFile('materials/lecture-preview.png')} style={{position:'absolute',right:120,top:25,height:650,width:520,objectFit:'contain'}}/>
</Frame>;

export const HomeworkPreview=()=>{
 const {fps}=useVideoConfig();
 return <Track name="截图整理 · 实际运行样段">
  <Sequence name="已上传的原创截图" durationInFrames={3*fps}><Shot file="image-input" title="一张截图，开始整理"/></Sequence>
  <Sequence name="真实识别的两项草稿" from={3*fps} durationInFrames={4*fps}><Shot file="image-draft" title="助手整理出两项作业"/></Sequence>
  <Sequence name="原草稿补充日期" from={7*fps} durationInFrames={4*fps}><Shot file="image-deadline" title="日期，可以确认或暂不填写"/></Sequence>
  <Sequence name="确认后的真实待办" from={11*fps} durationInFrames={2*fps}><Shot file="task-results" title="核对并确认后，进入待办"/></Sequence>
  <Sequence name="课间" from={13*fps} durationInFrames={2*fps}><Outro/></Sequence>
 </Track>;
};

// Silent editorial preview. Narration, captions and final export follow review.
export const CampusPromo=()=>{
 const {fps}=useVideoConfig();
 return <Track name="75 秒宣传片无声粗剪">
  <Sequence name="S01 信息聚合片头" durationInFrames={5*fps}><Intro/></Sequence>
  <Sequence name="S02 桌宠展开" from={5*fps} durationInFrames={3*fps}><DesktopShot file="pet-reveal" title="在桌面，随时打开"/></Sequence>
  <Sequence name="S02 完整今日窗口" from={8*fps} durationInFrames={3*fps}><Shot file="today-results" title="学习安排，集中在这里"/></Sequence>
  <Sequence name="S03 原创作业截图" from={11*fps} durationInFrames={4*fps}><Shot file="image-input" title="截图，变成待办"/></Sequence>
  <Sequence name="S03 真实识别草稿" from={15*fps} durationInFrames={5*fps}><Shot file="image-draft" title="先核对作业要求"/></Sequence>
  <Sequence name="S03 真实补充日期" from={20*fps} durationInFrames={4*fps}><Shot file="image-deadline" title="日期，可以之后补充"/></Sequence>
  <Sequence name="S03 已保存任务" from={24*fps} durationInFrames={5*fps}><Shot file="task-results" title="由你确认，再保存"/></Sequence>
  <Sequence name="S04 已有课程" from={29*fps} durationInFrames={3*fps}><Shot file="calendar-context" title="安排，与你的课程对齐"/></Sequence>
  <Sequence name="S04 真实安排草稿" from={32*fps} durationInFrames={6*fps}><Shot file="planning-draft" title="先看安排草稿"/></Sequence>
  <Sequence name="S04 确认后的今日安排" from={38*fps} durationInFrames={4*fps}><Shot file="today-results" title="确认后，进入日程"/></Sequence>
  <Sequence name="S05 按课程管理文件" from={42*fps} durationInFrames={5*fps}><Shot file="library-list" title="资料，按课程收好"/></Sequence>
  <Sequence name="S05 原创讲义" from={47*fps} durationInFrames={2*fps}><Lecture/></Sequence>
  <Sequence name="S05 真实回答与来源" from={49*fps} durationInFrames={5*fps}><Shot file="knowledge-answer" title="回答，带着原文来源"/></Sequence>
  <Sequence name="S06 人工确认记忆" from={54*fps} durationInFrames={7*fps}><Shot file="memory-confirm" title="学习偏好，由你确认后记住"/></Sequence>
  <Sequence name="S06 新会话召回" from={61*fps} durationInFrames={4*fps}><Shot file="memory-recall" title="新会话，继续记得"/></Sequence>
  <Sequence name="S07 真实桌宠待办" from={65*fps} durationInFrames={5*fps}><DesktopShot file="pet-result" title="今日待办，就在桌面"/></Sequence>
  <Sequence name="S08 品牌片尾" from={70*fps} durationInFrames={5*fps}><Outro/></Sequence>
 </Track>;
};
