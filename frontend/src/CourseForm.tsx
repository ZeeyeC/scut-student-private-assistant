import {useState} from 'react';
import type {Course} from './types';
import type {CourseSlot} from './course-slot';
import {Button} from './components/ui/button';

export function CourseForm({ onSave, initial }: { onSave: (c: Course) => Promise<void>; initial?: CourseSlot }) {
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
