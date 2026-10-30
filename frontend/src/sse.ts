export type PublicEvent = {
  run_id: string;
  seq: number;
  type: string;
  payload: Record<string, any>;
};
export function parseSseFrame(frame: string): PublicEvent | null {
  const data = frame
    .split("\n")
    .filter((l) => l.startsWith("data:"))
    .map((l) => l.slice(5).trimStart())
    .join("\n");
  return data ? JSON.parse(data) : null;
}
class SessionError extends Error {}
function backoff(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const abort = () => {
      clearTimeout(timer);
      reject(signal.reason);
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", abort);
      resolve();
    }, ms);
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
  });
}
export async function replayEvents(
  runId: string,
  after: number,
  onEvent: (e: PublicEvent) => void,
  signal: AbortSignal,
) {
  let cursor = after,
    retries = 0;
  while (!signal.aborted) {
    try {
      const r = await fetch(`/api/agent/runs/${runId}/events?after=${cursor}`, {
        credentials: "same-origin",
        signal,
      });
      if ([401, 403, 404].includes(r.status))
        throw new SessionError("聊天会话不可用，请刷新助手");
      if (!r.ok || !r.body) throw new Error("聊天连接失败");
      const reader = r.body.getReader(),
        decoder = new TextDecoder();
      let buffer = "";
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer = (buffer + decoder.decode(value, { stream: true })).replace(
            /\r\n/g,
            "\n",
          );
          let index;
          while ((index = buffer.indexOf("\n\n")) >= 0) {
            const frame = buffer.slice(0, index);
            buffer = buffer.slice(index + 2);
            const event = parseSseFrame(frame);
            if (!event || event.seq <= cursor) continue;
            onEvent(event);
            cursor = event.seq;
            retries = 0;
            if (["done", "error"].includes(event.type))
              return;
          }
        }
      } finally {
        await reader.cancel().catch(() => {});
      }
      const status = await fetch(`/api/agent/runs/${runId}`, {
        credentials: "same-origin",
        signal,
      });
      if ([401, 403, 404].includes(status.status))
        throw new SessionError("聊天会话不可用，请刷新助手");
      if(status.ok){
        const latest=(await status.json()).data;
        if(["done","failed","waiting_approval"].includes(latest.status) &&
           !(Number.isSafeInteger(latest.event_counter) && latest.event_counter>cursor))return;
      }
    } catch (error) {
      if (signal.aborted || error instanceof SessionError) throw error;
    }
    if (++retries > 5)
      throw new Error(
        "聊天连接中断，已生成的文字仍保留。请点击重新连接历史。",
      );
    await backoff(Math.min(250 * 2 ** (retries - 1), 2000), signal);
  }
}
