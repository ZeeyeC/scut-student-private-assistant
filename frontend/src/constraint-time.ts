import { DateTime } from "luxon";

export function constraintInput(value: string, timezone: string): string {
  return DateTime.fromISO(value).setZone(timezone).toFormat("yyyy-MM-dd'T'HH:mm");
}

export function constraintInstant(value: string, timezone: string): string {
  const parsed = DateTime.fromISO(value, { zone: timezone });
  if (!parsed.isValid || parsed.toFormat("yyyy-MM-dd'T'HH:mm") !== value)
    throw new Error("时间无效，或该时区因夏令时跳过了这个时间，请重新选择。");
  if (parsed.getPossibleOffsets().length > 1)
    throw new Error("该时区因夏令时有两个同名时间，请选择不重复的时间。");
  const result = parsed.toISO();
  if (!result) throw new Error("无法确定时间，请重新选择。");
  return result;
}
