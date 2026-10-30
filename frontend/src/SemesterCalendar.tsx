import {useState,type FormEvent} from 'react';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {api} from './api';
import type {Resource} from './types';
import {Button} from './components/ui/button';
import {DraftActions} from './ReviewedDraftActions';
import {ConflictReview} from './ConflictReview';
import {newSemesterForm,semesterPayload,semesterOperation,updateSemesterForm,type SemesterForm,type SemesterOperation} from './semester-calendar-state';

const kindNames:Record<string,string>={practice_week:'实践周',holiday:'学校节假日规则',makeup:'明确补课',custom:'其他学校规则'};
function when(event:any,timezone:string){
  if(!event)return '本次停课';
  const format=(v:string)=>new Date(v).toLocaleString('zh-CN',{timeZone:timezone,month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});
  return `${format(event.starts_at)} — ${format(event.ends_at)}${event.location?` · ${event.location}`:''}`;
}
export function SemesterCalendarReview({draft}:{draft:Resource}){
  const [error,setError]=useState('');
  const p=draft.data.payload,r=draft.data.source.preview;
  return <section className="card" aria-label="校历批量调整草稿">
    <p className="eyebrow">校历批量调整 · 尚未生效</p><h2>{p.operation==='undo'?'撤销校历批次':p.title}</h2>
    <p>{p.operation==='apply'?`${kindNames[p.rule_kind]} · ${p.source_scope}`:'恢复本批次之前的课程例外；后续修改受到保护'}</p>
    <p>依据：{p.reason}</p><p>共 {r.changes.length} 次课程 · 时区 {r.timezone}</p>
    {r.changes.map((change:any)=><div className="step" key={`${change.course_id}:${change.date}`}><h3>{change.title} · 原课日期 {change.date}</h3><p>调整前：{when(change.before,r.timezone)}</p><p>确认后：{when(change.after,r.timezone)}</p>{change.after?.teaching_intervals?.length>1&&<p>保留 {change.after.teaching_intervals.length} 段授课及原课间。</p>}</div>)}
    <ConflictReview report={r.conflict_report}/>
    {!!r.plan_conflicts?.length&&<div role="alert"><h3>新课程时间与这些学习安排重叠</h3>{r.plan_conflicts.map((e:any)=><p key={e.id}>{e.title??'学习安排'} · {when(e,r.timezone)}{e.locked?' · 已锁定':''}</p>)}</div>}
    {!!r.affected_plans?.length&&<p>有 {r.affected_plans.length} 项已有学习安排受影响，保存后请检查并重新规划。</p>}
    <p>{r.message}</p><DraftActions draft={draft} payload={p} onError={setError}/>
    {error&&<p role="alert">{error}。可取消草稿，按最新课程重新预览。</p>}
  </section>;
}
export function SemesterCalendar({timezone='Asia/Shanghai'}:{timezone?:string}){
  const q=useQueryClient();
  const courses=useQuery({queryKey:['courses'],queryFn:()=>api<Resource[]>('/courses')});
  const batches=useQuery({queryKey:['semester-calendars'],queryFn:()=>api<Resource[]>('/semester-calendars')});
  const [state,setState]=useState<{form:SemesterForm;operation:SemesterOperation|null}>({form:newSemesterForm(),operation:null});
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[created,setCreated]=useState<Resource|null>(null);
  const [undoOperations,setUndoOperations]=useState<Record<string,SemesterOperation>>({});
  const form=state.form;
  function update(patch:Partial<SemesterForm>){setState(s=>updateSemesterForm(s,patch));setError('');}
  async function submit(event:FormEvent){event.preventDefault();setError('');try{
    const op=state.operation??semesterOperation(semesterPayload(form));setState(s=>({...s,operation:op}));setBusy(true);
    const d=await api<Resource>('/drafts/semester-calendar',{method:'POST',headers:{'Idempotency-Key':op.key},body:JSON.stringify(op.body)});
    setCreated(d);setState(s=>({...s,operation:null}));await q.invalidateQueries({queryKey:['drafts']});
  }catch(e){setError(String(e));}finally{setBusy(false);}}
  return <section aria-label="学期校历与批量调课"><form className="card" onSubmit={submit}><h2>学校校历与批量调课</h2>
    <p>先填写你确认的学校通知和课程范围，再预览每一次课程。缺少学校校历时请先核实；系统不会按公共节假日猜补课日。日期按 {timezone} 解释。</p>
    <fieldset disabled={busy}>
      <label>规则类型<select required value={form.rule_kind} onChange={e=>update({rule_kind:e.target.value as SemesterForm['rule_kind']})}><option value="">请选择学校规则</option>{Object.entries(kindNames).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
      <label>通知名称<input required maxLength={200} value={form.title} onChange={e=>update({title:e.target.value})} placeholder="例如：本学期第二周实践安排"/></label>
      <label>规则依据<textarea required maxLength={1000} value={form.reason} onChange={e=>update({reason:e.target.value})} placeholder="填写学校/教师通知内容、日期或文件名"/></label>
      <label>通知作用范围<textarea required maxLength={1000} value={form.source_scope} onChange={e=>update({source_scope:e.target.value})} placeholder="例如：第2周，选中的理论课程停课；不包括实验课"/></label>
      <fieldset><legend>明确选择受影响课程</legend>{courses.error&&<p role="alert">{String(courses.error)}</p>}{courses.isPending&&<p>正在读取课程…</p>}{courses.data?.length===0&&<p>请先导入或添加课程。</p>}{courses.data?.map(course=><label className="check" key={course.id}><input type="checkbox" checked={form.course_ids.includes(course.id)} onChange={e=>update({course_ids:e.target.checked?[...form.course_ids,course.id]:form.course_ids.filter(id=>id!==course.id)})}/>{course.data.name} · 周{course.data.weekday} · {course.data.location??'教室未知'}</label>)}</fieldset>
      <label>调整方式<select value={form.action} onChange={e=>update({action:e.target.value as 'cancel'|'move'})}><option value="cancel">明确日期范围内停课</option><option value="move">明确原日 → 目标日补课</option></select></label>
      {form.action==='cancel'?<div className="grid2"><label>原课开始日期<input required type="date" value={form.start_date} onChange={e=>update({start_date:e.target.value})}/></label><label>原课结束日期（包含）<input required type="date" value={form.end_date} onChange={e=>update({end_date:e.target.value})}/></label></div>:<div>
        <p>每行表示原课表某一天的所选课程，统一移至明确的目标日，保留原节次和课间。多个原日可映射同一目标日，预览会列出重叠。</p>
        {form.mappings.map((m,index)=><div className="grid2" key={index}><label>原课日期 {index+1}<input required type="date" value={m.original_date} onChange={e=>update({mappings:form.mappings.map((row,i)=>i===index?{...row,original_date:e.target.value}:row)})}/></label><label>目标补课日期 {index+1}<input required type="date" value={m.target_date} onChange={e=>update({mappings:form.mappings.map((row,i)=>i===index?{...row,target_date:e.target.value}:row)})}/></label><Button type="button" variant="outline" onClick={()=>update({mappings:form.mappings.filter((_,i)=>i!==index)})}>移除第 {index+1} 行映射</Button></div>)}
        <Button type="button" variant="outline" onClick={()=>update({mappings:[...form.mappings,{original_date:'',target_date:''}]})}>添加日期映射</Button>
      </div>}
    </fieldset>
    {error&&<p role="alert">{error}。检查输入后可重新预览；网络错误可原样重试。</p>}<Button disabled={busy||!courses.data?.length}>{busy?'正在逐次预览…':state.operation?'重试预览':'预览批量调整'}</Button>
  </form>
  {created&&<div className="card" role="status">校历草稿已生成，请核对下方草稿中的 {created.data.source.preview.changes.length} 次课程后正式保存。</div>}
  <section className="card" aria-label="校历批次历史"><h2>已确认校历批次</h2>{batches.error&&<p role="alert">{String(batches.error)}</p>}{batches.data?.length===0&&<p>没有确认过学校校历规则。现有课表按已确认周次展开。</p>}
    {batches.data?.filter(row=>row.data.operation==='apply').map(row=><div className="step" key={row.id}><h3>{row.data.payload.title} · {kindNames[row.data.payload.rule_kind]}</h3><p>{row.data.payload.source_scope} · {row.data.targets.length} 次课程</p><p>依据：{row.data.payload.reason}</p><p>{new Date(row.data.confirmed_at).toLocaleString('zh-CN',{timeZone:timezone})} · {row.data.undone_by?'已撤销，原调整记录保留':'已生效'}</p>
      {!row.data.undone_by&&<Button type="button" variant="outline" disabled={busy} onClick={async()=>{
        const op=undoOperations[row.id]??semesterOperation({operation:'undo',batch_id:row.id,reason:'用户请求撤销本校历批次，恢复批次前的课程例外'});setUndoOperations(ops=>({...ops,[row.id]:op}));setBusy(true);setError('');
        try{const d=await api<Resource>('/drafts/semester-calendar',{method:'POST',headers:{'Idempotency-Key':op.key},body:JSON.stringify(op.body)});setCreated(d);await q.invalidateQueries({queryKey:['drafts']});setUndoOperations(ops=>{const copy={...ops};delete copy[row.id];return copy;});}
        catch(e){setError(String(e));}finally{setBusy(false);}
      }}>撤销整批（先预览）</Button>}
      <details><summary>查看原预览和调整范围</summary>{row.data.preview.changes.map((change:any)=><p key={`${change.course_id}:${change.date}`}>{change.title} · 原课 {change.date} · {when(change.before,row.data.preview.timezone)} → {when(change.after,row.data.preview.timezone)}</p>)}</details>
    </div>)}
  </section></section>;
}
