export type CampusPresetId = "wushan" | "guoji" | "daxuecheng";

export type CampusPreset = {
  id: CampusPresetId;
  label: string;
  classroom_open: string;
  morning_exercise: string;
  periods: Record<string, { start: string; end: string }>;
};

const WUSHAN_PERIODS: Record<string, { start: string; end: string }> = {
  "1": { start: "08:00", end: "08:45" },
  "2": { start: "08:55", end: "09:40" },
  "3": { start: "10:00", end: "10:45" },
  "4": { start: "10:55", end: "11:40" },
  "5": { start: "14:30", end: "15:15" },
  "6": { start: "15:25", end: "16:10" },
  "7": { start: "16:20", end: "17:05" },
  "8": { start: "17:15", end: "18:00" },
  "9": { start: "19:00", end: "19:45" },
  "10": { start: "19:55", end: "20:40" },
  "11": { start: "20:50", end: "21:35" },
  "12": { start: "21:35", end: "22:00" },
};

const GUOJI_DAXUECHENG_PERIODS: Record<string, { start: string; end: string }> = {
  "1": { start: "08:50", end: "09:35" },
  "2": { start: "09:40", end: "10:25" },
  "3": { start: "10:40", end: "11:25" },
  "4": { start: "11:30", end: "12:15" },
  "5": { start: "14:00", end: "14:45" },
  "6": { start: "14:50", end: "15:35" },
  "7": { start: "15:45", end: "16:30" },
  "8": { start: "16:35", end: "17:20" },
  "9": { start: "19:00", end: "19:45" },
  "10": { start: "19:55", end: "20:40" },
  "11": { start: "20:50", end: "21:35" },
  "12": { start: "21:35", end: "22:00" },
};

export const CAMPUS_PRESETS: CampusPreset[] = [
  {
    id: "wushan",
    label: "五山",
    classroom_open: "07:00",
    morning_exercise: "09:40-10:00",
    periods: WUSHAN_PERIODS,
  },
  {
    id: "guoji",
    label: "国际",
    classroom_open: "07:00",
    morning_exercise: "10:25-10:40",
    periods: GUOJI_DAXUECHENG_PERIODS,
  },
  {
    id: "daxuecheng",
    label: "大学城",
    classroom_open: "07:00",
    morning_exercise: "10:25-10:40",
    periods: GUOJI_DAXUECHENG_PERIODS,
  },
];

export function CampusPresetSelector({
  value,
  onChange,
  mode = "import",
}: {
  value: CampusPresetId | null | undefined;
  onChange: (next: CampusPresetId | null) => void;
  mode?: "import" | "settings";
}) {
  const activePreset = CAMPUS_PRESETS.find((p) => p.id === value) ?? null;
  const displayedPresets = activePreset ? [activePreset] : CAMPUS_PRESETS;
  return (
    <div className="campus-preset-selector">
      <label>
        校区节次模板
        <select
          aria-label="校区节次模板"
          value={value ?? ""}
          onChange={(e) =>
            onChange((e.target.value || null) as CampusPresetId | null)
          }
        >
          <option value="">
            {mode === "settings" ? "自定义节次时间" : "沿用当前节次设置 / 自定义"}
          </option>
          {CAMPUS_PRESETS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
      </label>
      <details className="campus-preset-schedule">
        <summary>
          查看12节作息时间表{activePreset ? `（${activePreset.label}）` : ""}
        </summary>
        {displayedPresets.map((preset) => (
          <div key={preset.id} className="campus-preset-schedule-card">
            <p className="muted">
              <strong>{preset.label}校区</strong> · 课室开放 {preset.classroom_open} · 课间操{" "}
              {preset.morning_exercise}（仅供参考，不计入排课节次）
            </p>
            <table>
              <thead>
                <tr>
                  <th>节次</th>
                  <th>时间</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(preset.periods).map(([num, span]) => (
                  <tr key={num}>
                    <td>第 {num} 节</td>
                    <td>
                      {span.start}-{span.end}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </details>
    </div>
  );
}
