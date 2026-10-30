import type {Page} from '@playwright/test';
const resource=(id:string,kind:string,data:Record<string,unknown>)=>({id,kind,revision:1,data});
const items=[
 ['math','高数 · 第三章习题','高等数学','2026-10-30T18:00:00+08:00',45,'14:00','完成第三章第 1–8 题，并整理两道错题。'],
 ['report','数据结构实验报告','数据结构','2026-10-31T18:00:00+08:00',60,'16:00','补充运行结果与复杂度分析。'],
 ['english','英语听力练习','大学英语','2026-10-30T23:59:00+08:00',20,'16:20','完成一组听力，整理生词。'],
 ['physics','物理实验预习','大学物理','2026-10-31T23:59:00+08:00',30,'19:00','阅读实验原理，填写预习记录。'],
 ['linear','线性代数复习','线性代数','2026-11-01T23:59:00+08:00',40,'','复习向量空间与线性变换。'],
 ['code','代码练习','数据结构','2026-11-01T23:59:00+08:00',45,'','练习二叉树遍历与递归。'],
 ['reading','英语阅读','大学英语','2026-11-02T23:59:00+08:00',25,'','阅读课文并完成练习。'],
 ['notes','整理本周课堂笔记','学习整理','2026-11-01T23:59:00+08:00',30,'','归纳本周知识点。'],
 ['preview','下周课程预习','学习整理','2026-11-01T23:59:00+08:00',35,'','提前查看下周课程材料。'],
] as const;
export async function visualFixture(page:Page,{taskCount=9,longTitle=false}:{taskCount?:number;longTitle?:boolean}={}){
 let visibleTaskCount=taskCount;
 await page.clock.setFixedTime(new Date('2026-10-30T05:30:00Z'));
 const tasks=items.map(([id,title,course,due,minutes,time,requirements])=>resource(id,'task',{title:longTitle?'长标题和English混排 '.repeat(8):title,course_id:course,due_at:due,due_text:null,deadline_basis:null,submission_method:null,requirements:[requirements],priority:2,status:'open',remedy_due_at:null}));
 const courses=[...new Set(items.map(t=>t[2]))].map(name=>resource(name,'course',{name,teacher:null,location:'A1-201',campus:null,weekday:1,weeks_text:'1-16周',periods:[1,2]}));
 const settings=resource('settings','settings',{timezone:'Asia/Shanghai',semester_name:'2026 秋季',week1_monday:'2026-09-07',week_count:16,daily_limit_minutes:180,max_block_minutes:60,min_block_minutes:15,buffer_minutes:10,periods:{1:{start:'09:00',end:'09:45'},2:{start:'09:50',end:'10:35'}},study_windows:[{start:'19:00',end:'21:00'}],campus_transfers:[]});
 const blocks=items.slice(0,4).map(([id,title,c,due,minutes,time])=>resource('block-'+id,'plan_block',{task_id:id,step_id:id+'-step',starts_at:`2026-10-30T${time}:00+08:00`,ends_at:`2026-10-30T${id==='math'?'14:45':id==='report'?'17:00':id==='english'?'16:40':'19:30'}:00+08:00`,status:'suggested',locked:false,title}));
 const dayEvents=[
  {id:'course-math',kind:'course',title:'高等数学',starts_at:'2026-10-30T09:00:00+08:00',ends_at:'2026-10-30T10:35:00+08:00',location:'A1-201',course_id:'高等数学'},
  {id:'study-structure',kind:'plan_block',title:'数据结构复习',starts_at:'2026-10-30T11:00:00+08:00',ends_at:'2026-10-30T11:25:00+08:00'},
  {id:'study-math',kind:'plan_block',title:'高数习题',starts_at:'2026-10-30T14:00:00+08:00',ends_at:'2026-10-30T14:45:00+08:00'},
  {id:'study-english',kind:'plan_block',title:'英语听力',starts_at:'2026-10-30T16:20:00+08:00',ends_at:'2026-10-30T16:40:00+08:00'},
 ];
 if(longTitle)dayEvents.forEach(event=>event.title='长标题和English混排 '.repeat(8));
 const studyEvents=[[26,14,'高数习题',45],[27,15,'实验报告',55],[28,14,'课程复习',55],[31,10,'实验报告',90]].map(([day,h,title,duration])=>({id:'study-'+day,kind:'plan_block',title,starts_at:`2026-10-${day}T${String(h).padStart(2,'0')}:00:00+08:00`,ends_at:`2026-10-${day}T${String(Number(h)+Math.floor(Number(duration)/60)).padStart(2,'0')}:${String(Number(duration)%60).padStart(2,'0')}:00+08:00`}));
 const weekEvents=[...dayEvents.filter(e=>e.kind==='course'||e.id==='study-math'),...studyEvents,...[[26,'高等数学','A1-201',9],[27,'大学英语','A3-302',10],[28,'数据结构','A2-105',9],[29,'线性代数','A1-206',10]].map(([day,title,location,h])=>({id:'course-'+day,kind:'course',title,location,course_id:title,starts_at:`2026-10-${day}T${String(h).padStart(2,'0')}:00:00+08:00`,ends_at:`2026-10-${day}T${String(Number(h)+1).padStart(2,'0')}:35:00+08:00`}))];
 const run=resource('run','agent_run',{thread_id:'thread',status:'done',approval_id:null,error:null});
 const table:Record<string,unknown>={
  '/app-mode':{mode:'local'},'/local/status':{selected:true,needs_selection:false,profiles:[]},'/local/session':{selected:true},'/me':{id:'fixture-user',email:'fixture@example.com'},'/csrf':{csrf_token:'synthetic-csrf'},
  '/tasks':tasks,'/plan-blocks':blocks,'/settings':settings,'/courses':courses,'/drafts':[],
  '/proactive/suggestions':{contract_version:'proactive-v1',preferences:{id:null,kind:'proactive_preferences',revision:0,contract_version:'proactive-v1',data:{enabled:false,categories:{},timezone:null,quiet_hours:null}},suggestions:[],suppression:'disabled',source_revision:1,capacity:null},'/duration-suggestions':{suggestions:[]},'/execution-timers':[],
  '/browser-imports':[], '/constraint-intents':[], '/after-class/open':{due:false,reason:'无需询问'},
  '/agent/threads':[resource('thread','agent_thread',{title:'今天的学习安排'})],'/agent/threads/thread/runs':[run],'/agent/runs/run':run,
  '/healthz':{database:true,text_model_configured:true,vision_model_configured:true},
 };
 await page.route('**/api/**',async route=>{
  const url=new URL(route.request().url()),path=url.pathname.slice(4);
  if(path==='/calendar-events'){const day=url.searchParams.get('start')===url.searchParams.get('end');await route.fulfill({json:{events:day?dayEvents:weekEvents,warnings:[],conflict_report:{issues:[]}}});return;}
  if(path==='/agent/runs/run/events'){
   const events=[{run_id:'run',seq:1,type:'message',payload:{message_id:'u',role:'user',content:'帮我安排今天剩下的学习任务。'}},{run_id:'run',seq:2,type:'message',payload:{message_id:'a',role:'assistant',content:'下午先完成高数习题，晚间留出一小时写实验报告。'}},{run_id:'run',seq:3,type:'done',payload:{}}];
   await route.fulfill({contentType:'text/event-stream',body:events.map(e=>'data: '+JSON.stringify(e)+'\n\n').join('')});return;
  }
  const match=path.match(/^\/tasks\/([^/]+)(\/steps)?$/);if(match){const task=tasks.find(t=>t.id===match[1]);const original=items.find(t=>t[0]===match[1]);await route.fulfill({json:match[2]?[resource(match[1]+'-step','step',{task_id:match[1],title:'完成练习',description:'合成参考',estimated_minutes:original?.[4]??30,status:'open',dependency_ids:[],acceptance_criteria:['完成'],spent_minutes:null})]:task});return;}
  if(path==='/tasks'){await route.fulfill({json:tasks.slice(0,visibleTaskCount)});return;}
  if(path in table){await route.fulfill({json:table[path]});return;}
  if(path.includes('/execution-summary')){await route.fulfill({json:{task_id:'math',step_id:null,actual_minutes:null,legacy_estimated_minutes:0,unresolved_legacy_minutes:0,planning_spent_minutes:0,unknown_step_ids:[],effective_record_ids:[],source_revision:1}});return;}
  // Read-only presentation fixture. Real writes are covered by integration tests.
  await route.fulfill({status:404,json:{detail:'Not part of the read-only visual fixture'}});
 });
 return {setTaskCount:(count:number)=>{visibleTaskCount=count;}};
}
