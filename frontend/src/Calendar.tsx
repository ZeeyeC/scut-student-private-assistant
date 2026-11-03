import { useState, useRef, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import FullCalendar from "@fullcalendar/react";
import timeGridPlugin from "@fullcalendar/timegrid";
import listPlugin from "@fullcalendar/list";
import luxonPlugin from "@fullcalendar/luxon3";
import interactionPlugin from "@fullcalendar/interaction";
import * as Dialog from "@radix-ui/react-dialog";
import { Button } from "./components/ui/button";
import { CourseIntervals } from "./CourseIntervals";
import { api } from "./api";
import type { Resource, Course, SettingsData } from "./types";
import { DraftReview } from "./DraftReview";
import { ChatPage } from "./Chat";
import { SmartSchedule } from "./SmartSchedule";
import type { ScheduleEvent } from "./schedule";
import { ScheduleShortcut } from "./ScheduleShortcut";
import { courseSlot, type CourseSlot } from "./course-slot";
import { CourseChangeForm, CourseChangeHistory } from "./CourseChanges";
import {CourseForm} from './CourseForm';
import {CampusTransfers, ConflictReview, type ConflictReport} from "./ConflictReview";

import {DetailPanel} from "./layout/DetailPanel";
import type {CalendarFilter} from "./layout/navigation";
import {DeleteFixedEvent} from "./DeleteFixedEvent";
import {FixedEvents} from "./Settings";
import {StudyTypes} from "./StudyTypes";
import { SemesterCalendar } from "./SemesterCalendar";
import {PageHeader} from './layout/PageHeader';
import {ChevronLeft,ChevronRight,Upload} from 'lucide-react';
import {scrollWithinWorkspace} from './layout/scrollWithin';

export function CalendarPage({focusDate,filter:requestedFilter,focusRequest=0}: {focusDate?: string; filter?:CalendarFilter; focusRequest?:number}) {
  const [filter,setFilter]=useState<CalendarFilter>(requestedFilter??'all');
  const [panel,setPanel]=useState<'plan'|'rules'|'fixed'|null>(null);
  const [detailOpen,setDetailOpen]=useState(false);
  const timetable=true;
  useEffect(()=>{if(requestedFilter)setFilter(requestedFilter);},[requestedFilter,focusRequest]);
  const included=(event:ScheduleEvent)=>filter==='all'||(filter==='courses'?event.kind==='course':event.kind==='plan_block');
  const calendar = useRef<FullCalendar>(null);
  const [narrowCalendar,setNarrowCalendar]=useState(()=>window.innerWidth<960);
  const [calendarTitle,setCalendarTitle]=useState('');
  useEffect(()=>{
    const query=window.matchMedia('(max-width: 959px)');
    const resize=()=>setNarrowCalendar(query.matches);
    query.addEventListener('change',resize);resize();
    return()=>query.removeEventListener('change',resize);
  },[]);
  useEffect(()=>{calendar.current?.getApi().changeView(narrowCalendar?'listWeek':'timeGridWeek');},[narrowCalendar]);
  useEffect(()=>{if(focusDate){calendar.current?.getApi().gotoDate(focusDate);}},[focusDate,focusRequest]);
  const q = useQueryClient();
  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: () => api<Resource>("/settings"),
  });
  const [range, setRange] = useState({
    start: new Date().toISOString().slice(0, 10),
    end: new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10),
  });
  const events = useQuery({
    queryKey: ["calendar-events", range],
    queryFn: () =>
      api<{events: ScheduleEvent[]; warnings: string[]; conflict_report:ConflictReport}>(`/calendar-events?start=${range.start}&end=${range.end}`),
  });
  const drafts = useQuery({
    queryKey: ["drafts"],
    queryFn: () => api<Resource[]>("/drafts"),
  });
  const [adjustCourse, setAdjustCourse] = useState(false);
  useEffect(()=>{ const saved=()=>{setSelected(null);setAdjustCourse(false);};window.addEventListener("campus-course-change-saved",saved);return()=>window.removeEventListener("campus-course-change-saved",saved); },[]);
  const [selected, setSelected] = useState<ScheduleEvent | null>(null);
  const [slot, setSlot] = useState<CourseSlot | null>(null);
  const [newDraft, setNewDraft] = useState("");
  const zone=settings.data?.data.timezone??'Asia/Shanghai';
  const hour=(value:string)=>Number(new Date(value).toLocaleTimeString('en-GB',{timeZone:zone,hour:'2-digit',hour12:false}));
  const crossesDay=(events.data?.events??[]).some(e=>new Date(e.starts_at).toLocaleDateString('en-CA',{timeZone:zone})!==new Date(e.ends_at).toLocaleDateString('en-CA',{timeZone:zone}));
  const firstHour=crossesDay?0:Math.min(9,...(events.data?.events??[]).map(e=>hour(e.starts_at)));
  const lastHour=crossesDay?24:Math.max(19,...(events.data?.events??[]).map(e=>Math.min(24,hour(e.ends_at)+1)));
  useEffect(() => {
    if (!newDraft) return;
    const element = document.getElementById(`timetable-draft-${newDraft}`);
    if (element) {
      scrollWithinWorkspace(element);
      element.focus({ preventScroll: true });
      setNewDraft("");
    }
  }, [newDraft, drafts.data]);
  async function saveCourse(course: Course) {
    const draft = await api<Resource>("/drafts/timetable", {
      method: "POST",
      body: JSON.stringify({ courses: [course], semester_label: "手工录入", completeness: "partial" }),
    });
    setSlot(null);
    setNewDraft(draft.id);
    window.dispatchEvent(new Event('campus-start-import'));
    await q.invalidateQueries({ queryKey: ["drafts"] });
  }
  return (
    <>
      <PageHeader title="日程"><Button variant="outline" onClick={()=>window.dispatchEvent(new Event('campus-start-import'))}><Upload size={16}/>导入课表</Button><Button aria-label="安排学习" onClick={()=>setPanel('plan')}>安排</Button></PageHeader>
      <div className="workspace-tabs calendar-filters" aria-label="日程筛选">{([['all','全部'],['courses','课程'],['study','学习']] as const).map(([id,label])=><button type="button" key={id} aria-pressed={filter===id} onClick={()=>setFilter(id)}>{label}</button>)}</div>
      <div className="calendar-toolbar"><div className="calendar-date-controls"><strong className="fc-toolbar-title">{calendarTitle}</strong><button type="button" className="calendar-date-icon" aria-label="上一周" onClick={()=>calendar.current?.getApi().prev()}><ChevronLeft size={16}/></button><button type="button" className="calendar-date-icon" aria-label="下一周" onClick={()=>calendar.current?.getApi().next()}><ChevronRight size={16}/></button><button type="button" className="workspace-text-button" onClick={()=>calendar.current?.getApi().today()}>本周</button></div>
        <div className="calendar-secondary-actions"><button type="button" className="workspace-text-button" onClick={()=>setPanel('rules')}>课程规则</button><button type="button" className="workspace-text-button" onClick={()=>setPanel('fixed')}>固定事项</button></div>
      </div>
      {events.data?.conflict_report && events.data.conflict_report.issues.length>0 && <div className="card"><p>当前显示日期内的课程与固定事项检查</p><ConflictReview report={events.data.conflict_report} timezone={settings.data?.data.timezone} /></div>}
      <div className="workspace-calendar">
        {events.error && <p role="alert">{String(events.error)}</p>}
        {events.isPending && <p role="status">正在读取日程…</p>}
        {events.data?.warnings.map((w,i)=><p role="alert" key={i}>{w}</p>)}
        <FullCalendar
          ref={calendar}
          initialDate={focusDate}
          firstDay={1}
          plugins={[timeGridPlugin, listPlugin, luxonPlugin, interactionPlugin]}
          timeZone={settings.data?.data.timezone ?? "Asia/Shanghai"}
          initialView={narrowCalendar ? "listWeek" : "timeGridWeek"}
          headerToolbar={false}
          buttonText={{ today: "今天", week: "周", list: "列表" }}
          locale="zh-cn"
          allDaySlot={false}
          height={narrowCalendar ? "auto" : 542}
          scrollTime={focusDate ? new Date(focusDate).toLocaleTimeString("en-GB", {timeZone: settings.data?.data.timezone ?? "Asia/Shanghai", hour12: false}) : "07:00:00"}
          slotMinTime={`${String(firstHour).padStart(2,'0')}:00:00`}
          slotMaxTime={`${String(lastHour).padStart(2,'0')}:00:00`}
          slotDuration="00:30:00"
          slotLabelInterval="01:00:00"
          slotLabelFormat={{hour:'2-digit',minute:'2-digit',hour12:false}}
          dayHeaderContent={info=><div className="calendar-day-heading"><span>{info.date.toLocaleDateString('zh-CN',{weekday:'short',timeZone:zone})}</span><b>{info.date.toLocaleDateString('zh-CN',{day:'numeric',timeZone:zone}).replace('日','')}</b></div>}
          eventContent={info=><><strong>{info.event.extendedProps.record.title}</strong>{info.event.extendedProps.record.location&&<small>{info.event.extendedProps.record.location}</small>}</>}
          dateClick={info => {
            if (!timetable || info.allDay || info.view.type !== "timeGridWeek") return;
            setSlot(courseSlot(info.dateStr, settings.data?.data as SettingsData | undefined));
            setSelected(null);
          }}
          events={(events.data?.events ?? []).filter(included).map((e) => ({
            ...e,
            title: e.title,
            start: e.starts_at,
            end: e.ends_at,
            backgroundColor: e.kind === "plan_block" ? "var(--workspace-selected)" : "var(--workspace-soft)",
            borderColor: "transparent",
            classNames:[e.kind==='plan_block'?'workspace-study-event':'workspace-course-event',...(Date.parse(e.ends_at)-Date.parse(e.starts_at)<1800000?['workspace-short-event']:[])],
            extendedProps: {record: e},
          }))}
          eventClick={info => {setSelected(info.event.extendedProps.record);setAdjustCourse(false);setDetailOpen(true);}}
          datesSet={(info) => {
            setRange({
              start: info.startStr.slice(0, 10),
              end: info.endStr.slice(0, 10),
            });
            const end=new Date(info.end.getTime()-1);
            const fmt=(d:Date)=>d.toLocaleDateString('zh-CN',{month:'long',day:'numeric',timeZone:zone});
            setCalendarTitle(`${fmt(info.start)}–${fmt(end)}`);
          }}
        />
        {events.data && events.data.events.filter(included).length === 0 && (
          <p>{timetable ? "当前筛选下暂无安排。" : "本周暂无安排。先添加待办、补齐耗时或步骤，再点击智能安排。"}</p>
        )}
      </div>
      <DetailPanel open={detailOpen} title={selected?.title??"日程详情"} onClose={()=>setDetailOpen(false)}>{selected&&<section aria-label="日程详情">
        <h2>{selected.title}</h2>
        <p>{new Date(selected.starts_at).toLocaleString("zh-CN",{timeZone: settings.data?.data.timezone ?? "Asia/Shanghai"})}–{new Date(selected.ends_at).toLocaleString("zh-CN",{timeZone: settings.data?.data.timezone ?? "Asia/Shanghai"})}</p>
        <p>{selected.kind === "course" ? "课程" : selected.kind === "fixed_event" ? "固定事项" : selected.kind === "scheduling_constraint" ? "禁排时段 · 仅约束后续任务规划，不触发提醒" : "学习安排"} {selected.location}</p>
        {selected.kind === "course" && <CourseIntervals event={selected} timezone={settings.data?.data.timezone ?? "Asia/Shanghai"} />}
        {selected.course_id&&<StudyTypes targetId={selected.course_id}/>}
        {timetable && selected.kind === "course" && selected.course_id && <CourseCampusEditor key={selected.course_id} courseId={selected.course_id} onCreated={async id=>{setNewDraft(id);setDetailOpen(false);window.dispatchEvent(new Event('campus-start-import'));setSelected(null);await q.invalidateQueries({queryKey:["drafts"]});}} />}
        {selected.kind === "fixed_event" && selected.revision !== undefined && <DeleteFixedEvent key={selected.id} id={selected.id} revision={selected.revision} title={selected.title} onDeleted={()=>{setDetailOpen(false);setSelected(null);}} />}
        {selected.kind !== "scheduling_constraint" && <ScheduleShortcut key={`${selected.id}:${selected.starts_at}`} event={selected} />}
        {selected.kind === "course" && <><p>{selected.adjusted ? "本次课程已调整 · " : ""}原课日期 {selected.original_date}</p><Button variant="outline" onClick={()=>setAdjustCourse(!adjustCourse)}>调课或停课</Button></>}

        {selected.kind === "course" && adjustCourse && <CourseChangeForm key={selected.id} event={selected} timezone={settings.data?.data.timezone??"Asia/Shanghai"} onClose={()=>{setAdjustCourse(false);window.dispatchEvent(new Event("campus-open-review"));setDetailOpen(false);}} />}
      </section>}</DetailPanel>
      <DetailPanel open={panel==='plan'} title="安排学习" onClose={()=>setPanel(null)}><SmartSchedule/></DetailPanel>
      <DetailPanel open={panel==='fixed'} title="固定事项" onClose={()=>setPanel(null)}><FixedEvents/><div className="fixed-event-chat"><ChatPage embedded/></div></DetailPanel>
      <DetailPanel open={panel==='rules'} title="课程规则" onClose={()=>setPanel(null)}><CampusTransfers/>

      <SemesterCalendar timezone={settings.data?.data.timezone??"Asia/Shanghai"} />
      <CourseChangeHistory timezone={settings.data?.data.timezone??"Asia/Shanghai"} />
      {drafts.data?.filter(d=>["course_change", "semester_calendar"].includes(d.data.draft_kind)).map(d=><DraftReview draft={d} key={d.id+":"+d.revision} />)}
      </DetailPanel>
      <Dialog.Root open={slot !== null} onOpenChange={open => { if (!open) setSlot(null); }}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="import-dialog course-slot-dialog" onOpenAutoFocus={event => {
            event.preventDefault();
            document.querySelector<HTMLInputElement>('.course-slot-dialog input[name="name"]')?.focus();
          }}>
            <header>
              <Dialog.Title>添加课程</Dialog.Title>
              <Dialog.Close asChild><Button variant="outline">取消</Button></Dialog.Close>
            </header>
            <Dialog.Description>
              已选择 {slot?.date} {slot?.time}（{settings.data?.data.timezone ?? "Asia/Shanghai"}）。默认仅添加到所选教学周，可修改周次和节次。
            </Dialog.Description>
            {slot?.notice && <p role="status">{slot.notice}</p>}
            {slot && <CourseForm key={`${slot.date}-${slot.time}`} initial={slot} onSave={saveCourse} />}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}
function CourseCampusEditor({courseId,onCreated}:{courseId:string;onCreated:(id:string)=>Promise<void>}) {
  const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState("");
  const courses=useQuery({queryKey:["courses"],queryFn:()=>api<Resource[]>("/courses"),enabled:open});
  const course=courses.data?.find(c=>c.id===courseId);
  return <div>
    <Button variant="outline" onClick={()=>setOpen(!open)}>{open?"收起课程校区":"补充或修改整门课程校区"}</Button>
    {open && courses.error && <p role="alert">{String(courses.error)}</p>}
    {open && course && <form aria-label="编辑整门课程校区" onSubmit={async e=>{
      e.preventDefault();setBusy(true);setError("");
      const campus=String(new FormData(e.currentTarget).get("campus")).trim() || null;
      try {const d=await api<Resource>("/drafts/timetable",{method:"POST",body:JSON.stringify({semester_label:"补充课程校区",completeness:"partial",courses:[{...course.data,campus}]})});await onCreated(d.id);}
      catch(e){setError(String(e));}finally{setBusy(false);}
    }}>
      <p>修改 {course.data.name} 在全部教学周的固定校区，先生成草稿再确认。单次调课已确认的校区仍按原调整保留。</p>
      <label>整门课程校区<input name="campus" maxLength={100} defaultValue={course.data.campus??""} placeholder="未知可留空" /></label>
      <Button disabled={busy}>{busy?"正在生成…":"生成校区校对草稿"}</Button>
      {error&&<p role="alert">{error}</p>}
    </form>}
  </div>;
}
