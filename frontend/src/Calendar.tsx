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
import { AssignmentsPage } from "./Assignments";
import { SmartSchedule } from "./SmartSchedule";
import type { ScheduleEvent } from "./schedule";
import { ScheduleShortcut } from "./ScheduleShortcut";
import { courseSlot, type CourseSlot } from "./course-slot";
import { CourseChangeForm, CourseChangeHistory } from "./CourseChanges";
import { TimetableRecognitionInput } from "./TimetableRecognition";
import {CampusTransfers, ConflictReview, type ConflictReport} from "./ConflictReview";

export function CalendarPage({focusDate, mode = "timetable"}: {focusDate?: string; mode?: "timetable" | "schedule"}) {
  const timetable = mode === "timetable";
  const calendar = useRef<FullCalendar>(null);
  useEffect(()=>{if(focusDate){calendar.current?.getApi().gotoDate(focusDate);setChat(false);}},[focusDate]);
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
  const [manual, setManual] = useState(false);
  const [chat, setChat] = useState(false);
  const [adjustCourse, setAdjustCourse] = useState(false);
  useEffect(()=>{ const saved=()=>{setSelected(null);setAdjustCourse(false);};window.addEventListener("campus-course-change-saved",saved);return()=>window.removeEventListener("campus-course-change-saved",saved); },[]);
  const [selected, setSelected] = useState<ScheduleEvent | null>(null);
  const [slot, setSlot] = useState<CourseSlot | null>(null);
  const [newDraft, setNewDraft] = useState("");
  useEffect(() => {
    if (!newDraft) return;
    const element = document.getElementById(`timetable-draft-${newDraft}`);
    if (element) {
      element.scrollIntoView({ block: "center" });
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
    setManual(false);
    setNewDraft(draft.id);
    await q.invalidateQueries({ queryKey: ["drafts"] });
  }
  return (
    <>
      <div className="page-head">
        <div>
          <p className="eyebrow">YOUR WEEK</p>
          <h1>{timetable ? "课表" : "待办与日程"}</h1>
          <p>{timetable ? "人工设定的固定课程；智能排程会避让这些时间。" : "待办任务与智能学习安排，并包含固定课表和事项。"}</p>
        </div>
        {timetable && <Button
          onClick={() => window.dispatchEvent(new Event("campus-start-import"))}
        >
          导入华工课表
        </Button>}
      </div>
      {!timetable && <SmartSchedule />}
      {!timetable && <Button onClick={() => setChat(!chat)}>{chat ? "收起事项对话" : "用 AI 添加固定事项"}</Button>}
      {!timetable && chat && <ChatPage embedded />}
      <p>{timetable ? "这里只显示固定课程。点击周视图空白格添加课程，点击已有课程查看详情；也可使用下方手工添加。" : "蓝色：固定课程 · 紫色：固定事项 · 绿色：智能学习安排 · 灰色：禁排时段。课程仅作固定时间参考，不会被智能排程移动；点击条目可查看详情。"}</p>
      {timetable && <p>
        已适配本人实测的华工个人课表。请先在设置中校对开学周一、学期周数和节次时间。
      </p>}
      {timetable && <CampusTransfers />}
      {events.data?.conflict_report && events.data.conflict_report.issues.length>0 && <div className="card"><p>当前显示日期内的课程与固定事项检查</p><ConflictReview report={events.data.conflict_report} timezone={settings.data?.data.timezone} /></div>}
      <div className="card">
        {events.error && <p role="alert">{String(events.error)}</p>}
        {events.isPending && <p role="status">正在读取日程…</p>}
        {events.data?.warnings.map((w,i)=><p role="alert" key={i}>{w}</p>)}
        <FullCalendar
          ref={calendar}
          initialDate={focusDate}
          firstDay={1}
          plugins={[timeGridPlugin, listPlugin, luxonPlugin, interactionPlugin]}
          timeZone={settings.data?.data.timezone ?? "Asia/Shanghai"}
          initialView={window.innerWidth < 768 ? "listWeek" : "timeGridWeek"}
          headerToolbar={{
            left: "prev,next today",
            center: "title",
            right: "timeGridWeek,listWeek",
          }}
          buttonText={{ today: "今天", week: "周", list: "列表" }}
          locale="zh-cn"
          allDaySlot={false}
          height={window.innerWidth < 768 ? "auto" : 680}
          scrollTime={focusDate ? new Date(focusDate).toLocaleTimeString("en-GB", {timeZone: settings.data?.data.timezone ?? "Asia/Shanghai", hour12: false}) : "07:00:00"}
          slotMinTime="00:00:00"
          slotMaxTime="24:00:00"
          slotDuration="00:30:00"
          dateClick={info => {
            if (!timetable || info.allDay || info.view.type !== "timeGridWeek") return;
            setSlot(courseSlot(info.dateStr, settings.data?.data as SettingsData | undefined));
            setSelected(null);
          }}
          events={(events.data?.events ?? []).filter(e => !timetable || e.kind === "course").map((e) => ({
            ...e,
            title: e.title + (e.location ? " · " + e.location : ""),
            start: e.starts_at,
            end: e.ends_at,
            backgroundColor: e.kind === "course" ? "#2563eb" : e.kind === "fixed_event" ? "#7c3aed" : e.kind === "scheduling_constraint" ? "#64748b" : "#007c74",
            borderColor: "transparent",
            extendedProps: {record: e},
          }))}
          eventClick={info => {setSelected(info.event.extendedProps.record);setAdjustCourse(false);}}
          datesSet={(info) =>
            setRange({
              start: info.startStr.slice(0, 10),
              end: info.endStr.slice(0, 10),
            })
          }
        />
        {events.data && events.data.events.filter(e => !timetable || e.kind === "course").length === 0 && (
          <p>{timetable ? "本周还没有课程。可点击周视图空白格、手工添加或导入课表。" : "本周暂无安排。先添加待办、补齐耗时或步骤，再点击智能安排。"}</p>
        )}
      </div>
      {selected && <section className="card" aria-label="日程详情">
        <h2>{selected.title}</h2>
        <p>{new Date(selected.starts_at).toLocaleString("zh-CN",{timeZone: settings.data?.data.timezone ?? "Asia/Shanghai"})}–{new Date(selected.ends_at).toLocaleString("zh-CN",{timeZone: settings.data?.data.timezone ?? "Asia/Shanghai"})}</p>
        <p>{selected.kind === "course" ? "课程" : selected.kind === "fixed_event" ? "固定事项" : selected.kind === "scheduling_constraint" ? "禁排时段 · 仅约束后续任务规划，不触发提醒" : "学习安排"} {selected.location}</p>
        {selected.kind === "course" && <CourseIntervals event={selected} timezone={settings.data?.data.timezone ?? "Asia/Shanghai"} />}
        {timetable && selected.kind === "course" && selected.course_id && <CourseCampusEditor key={selected.course_id} courseId={selected.course_id} onCreated={async id=>{setNewDraft(id);setSelected(null);await q.invalidateQueries({queryKey:["drafts"]});}} />}
        {selected.kind !== "scheduling_constraint" && <ScheduleShortcut key={`${selected.id}:${selected.starts_at}`} event={selected} />}
        {selected.kind === "course" && <><p>{selected.adjusted ? "本次课程已调整 · " : ""}原课日期 {selected.original_date}</p><Button variant="outline" onClick={()=>setAdjustCourse(!adjustCourse)}>调课或停课</Button></>}
        <Button variant="outline" onClick={()=>{setSelected(null);setAdjustCourse(false);}}>关闭详情</Button>
        {selected.kind === "course" && adjustCourse && <CourseChangeForm key={selected.id} event={selected} timezone={settings.data?.data.timezone??"Asia/Shanghai"} onClose={()=>setAdjustCourse(false)} />}
      </section>}
      {!timetable && <AssignmentsPage embedded />}
      {timetable && <>
      <CourseChangeHistory timezone={settings.data?.data.timezone??"Asia/Shanghai"} />
      {drafts.data?.filter(d=>d.data.draft_kind==="course_change").map(d=><DraftReview draft={d} key={d.id+":"+d.revision} />)}
      <Button variant="outline" onClick={() => setChat(!chat)}>{chat ? "收起课表对话" : "用文字添加课表"}</Button>
      {chat && <ChatPage embedded courseEntry />}
      <TimetableRecognitionInput />
      <Button variant="outline" onClick={() => setManual(!manual)}>
        手工添加课程
      </Button>
      {manual && <CourseForm onSave={saveCourse} />}
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
      {drafts.data
        ?.filter((d) => ["timetable", "timetable_recognition", "timetable_text"].includes(d.data.draft_kind) && !(chat && d.data.draft_kind === "timetable_text"))
        .map((d) => (
          <div key={d.id} id={`timetable-draft-${d.id}`} tabIndex={-1}><DraftReview draft={d} /></div>
        ))}
      </>}
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
function CourseForm({ onSave, initial }: { onSave: (c: Course) => Promise<void>; initial?: CourseSlot }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <form
      className="card"
      onSubmit={async (e) => {
        e.preventDefault();
        if (busy) return;
        const f = new FormData(e.currentTarget);
        setBusy(true); setError("");
        try { await onSave({
          source_key: crypto.randomUUID(),
          name: String(f.get("name")),
          weekday: Number(f.get("weekday")),
          weeks: String(f.get("weeks")).split(",").map(Number),
          periods: String(f.get("periods")).split(",").map(Number),
          location: String(f.get("location")),
          campus: String(f.get("campus")) || null,
        }); } catch (e) { setError(String(e)); } finally { setBusy(false); }
      }}
    >
      {!initial && <h2>添加一门课程</h2>}
      <label>
        课程名称
        <input name="name" required />
      </label>
      <div className="grid2">
        <label>
          星期
          <select name="weekday" defaultValue={initial?.weekday ?? 1}>
            {["一", "二", "三", "四", "五", "六", "日"].map((n, i) => (
              <option key={n} value={i + 1}>
                星期{n}
              </option>
            ))}
          </select>
        </label>
        <label>
          校区
          <input name="campus" maxLength={100} placeholder="按实际校区填写，可稍后补充" />
        </label>
        <label>
          地点
          <input name="location" />
        </label>
        <label>
          周次（逗号分隔）
          <input name="weeks" required placeholder="1,3,5,7" defaultValue={initial?.weeks ?? ""} />
        </label>
        <label>
          节次（逗号分隔）
          <input name="periods" required placeholder="1,2" defaultValue={initial?.periods ?? ""} />
        </label>
      </div>
      {error && <p role="alert">{error}</p>}
      <Button disabled={busy}>{busy ? "正在生成…" : "生成校对草稿"}</Button>
    </form>
  );
}
