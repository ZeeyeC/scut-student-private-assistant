import { useState, useRef, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import FullCalendar from "@fullcalendar/react";
import timeGridPlugin from "@fullcalendar/timegrid";
import listPlugin from "@fullcalendar/list";
import luxonPlugin from "@fullcalendar/luxon3";
import { Button } from "./components/ui/button";
import { api } from "./api";
import type { Resource, Course } from "./types";
import { DraftReview } from "./DraftReview";
import { ChatPage } from "./Chat";
import { TodoList } from "./TodoList";
import type { ScheduleEvent } from "./schedule";

export function CalendarPage({focusDate}: {focusDate?: string}) {
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
      api<{events: ScheduleEvent[]; warnings: string[]}>(`/calendar-events?start=${range.start}&end=${range.end}`),
  });
  const drafts = useQuery({
    queryKey: ["drafts"],
    queryFn: () => api<Resource[]>("/drafts"),
  });
  const [error, setError] = useState("");
  const [manual, setManual] = useState(false);
  const [chat, setChat] = useState(false);
  const [selected, setSelected] = useState<ScheduleEvent | null>(null);
  return (
    <>
      <div className="page-head">
        <div>
          <p className="eyebrow">YOUR WEEK</p>
          <h1>课表</h1>
          <p>课程、固定事项和已确认的学习安排，集中在一张日历。</p>
        </div>
        <Button
          onClick={() => window.dispatchEvent(new Event("campus-start-import"))}
        >
          导入华工课表
        </Button>
      </div>
      <Button onClick={() => setChat(!chat)}>{chat ? "收起事项对话" : "用 AI 添加事项"}</Button>
      {chat && <ChatPage embedded />}
      <p>蓝色：课程 · 紫色：固定事项 · 绿色：学习安排。点击日历条目查看详情。</p>
      <p>
        已适配本人实测的华工个人课表。请先在设置中校对开学周一、学期周数和节次时间。
      </p>
      {error && <p role="alert">{error}</p>}
      <div className="card">
        {events.error && <p role="alert">{String(events.error)}</p>}
        {events.isPending && <p role="status">正在读取日程…</p>}
        {events.data?.warnings.map((w,i)=><p role="alert" key={i}>{w}</p>)}
        <FullCalendar
          ref={calendar}
          initialDate={focusDate}
          firstDay={1}
          plugins={[timeGridPlugin, listPlugin, luxonPlugin]}
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
          events={(events.data?.events ?? []).map((e) => ({
            ...e,
            title: e.title + (e.location ? " · " + e.location : ""),
            start: e.starts_at,
            end: e.ends_at,
            backgroundColor: e.kind === "course" ? "#2563eb" : e.kind === "fixed_event" ? "#7c3aed" : "#007c74",
            borderColor: "transparent",
            extendedProps: {record: e},
          }))}
          eventClick={info => setSelected(info.event.extendedProps.record)}
          datesSet={(info) =>
            setRange({
              start: info.startStr.slice(0, 10),
              end: info.endStr.slice(0, 10),
            })
          }
        />
        {events.data?.events.length === 0 && (
          <p>本周还没有课程或事项。可导入课表，或点击“用 AI 添加事项”。</p>
        )}
      </div>
      {selected && <section className="card" aria-label="日程详情">
        <h2>{selected.title}</h2>
        <p>{new Date(selected.starts_at).toLocaleString("zh-CN",{timeZone: settings.data?.data.timezone ?? "Asia/Shanghai"})}–{new Date(selected.ends_at).toLocaleString("zh-CN",{timeZone: settings.data?.data.timezone ?? "Asia/Shanghai"})}</p>
        <p>{selected.kind === "course" ? "课程" : selected.kind === "fixed_event" ? "固定事项" : "学习安排"} {selected.location}</p>
        <Button variant="outline" onClick={()=>setSelected(null)}>关闭详情</Button>
      </section>}
      <TodoList />
      <Button variant="outline" onClick={() => setManual(!manual)}>
        手工添加课程
      </Button>
      {manual && (
        <CourseForm
          onSave={async (course) => {
            try {
              await api("/drafts/timetable", {
                method: "POST",
                body: JSON.stringify({
                  courses: [course],
                  semester_label: "手工录入",
                  completeness: "partial",
                }),
              });
              setManual(false);
              q.invalidateQueries({ queryKey: ["drafts"] });
            } catch (e) {
              setError(String(e));
            }
          }}
        />
      )}{" "}
      {drafts.data
        ?.filter((d) => d.data.draft_kind === "timetable")
        .map((d) => (
          <DraftReview key={d.id} draft={d} />
        ))}
    </>
  );
}
function CourseForm({ onSave }: { onSave: (c: Course) => void }) {
  return (
    <form
      className="card"
      onSubmit={(e) => {
        e.preventDefault();
        const f = new FormData(e.currentTarget);
        onSave({
          source_key: crypto.randomUUID(),
          name: String(f.get("name")),
          weekday: Number(f.get("weekday")),
          weeks: String(f.get("weeks")).split(",").map(Number),
          periods: String(f.get("periods")).split(",").map(Number),
          location: String(f.get("location")),
        });
      }}
    >
      <h2>添加一门课程</h2>
      <label>
        课程名称
        <input name="name" required />
      </label>
      <div className="grid2">
        <label>
          星期
          <select name="weekday">
            {["一", "二", "三", "四", "五", "六", "日"].map((n, i) => (
              <option key={n} value={i + 1}>
                星期{n}
              </option>
            ))}
          </select>
        </label>
        <label>
          地点
          <input name="location" />
        </label>
        <label>
          周次（逗号分隔）
          <input name="weeks" required placeholder="1,3,5,7" />
        </label>
        <label>
          节次（逗号分隔）
          <input name="periods" required placeholder="1,2" />
        </label>
      </div>
      <Button>生成校对草稿</Button>
    </form>
  );
}
