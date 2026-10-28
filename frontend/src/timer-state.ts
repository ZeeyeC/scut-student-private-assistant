export function formatElapsed(seconds: number) {
  const n = Math.max(0, Math.floor(seconds));
  return [Math.floor(n / 3600), Math.floor(n / 60) % 60, n % 60].map(v => String(v).padStart(2, "0")).join(":");
}

export function timerElapsed(timer: {status: string; elapsed_seconds: number}, receivedAt: number, current: number) {
  return timer.elapsed_seconds + (timer.status === "running" ? Math.min(120, Math.max(0, (current - receivedAt) / 1000)) : 0);
}

const locks = new Map<string, Promise<unknown>>();
export function serializeTimerAction<T>(id: string, work: () => Promise<T>): Promise<T> {
  const previous = locks.get(id) ?? Promise.resolve();
  const next = previous.catch(() => {}).then(work);
  locks.set(id, next);
  void next.finally(() => {if (locks.get(id) === next) locks.delete(id);}).catch(() => {});
  return next;
}
