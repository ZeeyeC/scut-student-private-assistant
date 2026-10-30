import { it, expect } from "vitest";
import { parseSseFrame } from "./sse";
it("parses public event with unicode and ignores heartbeat", () => {
  expect(parseSseFrame(": keepalive")).toBeNull();
  expect(
    parseSseFrame(
      'id: 2\nevent: message\ndata: {"run_id":"r","seq":2,"type":"message","payload":{"content":"已提取"}}',
    ),
  ).toEqual({
    run_id: "r",
    seq: 2,
    type: "message",
    payload: { content: "已提取" },
  });
});

it("reconnects from the last delivered cursor after a truncated stream", async () => {
  const { vi } = await import("vitest");
  const { replayEvents } = await import("./sse");
  const frame = (seq: number, type: string, payload: object) => `data: ${JSON.stringify({run_id: "r", seq, type, payload})}\n\n`;
  const calls: string[] = [];
  const replies = [
    new Response(frame(1, "message_delta", {message_id: "m", delta: "已"})),
    Response.json({data: {status: "running"}}),
    new Response(frame(2, "message_delta", {message_id: "m", delta: "生成"}) + frame(3, "done", {})),
  ];
  vi.stubGlobal("fetch", async (url: string) => {calls.push(url); return replies.shift()!;});
  try {
    const events: number[] = [];
    await replayEvents("r", 0, e => events.push(e.seq), new AbortController().signal);
    expect(events).toEqual([1, 2, 3]);
    expect(calls).toContain("/api/agent/runs/r/events?after=1");
  } finally {vi.unstubAllGlobals();}
});

it("replays past an old approval when its run has already finished", async () => {
  const { vi } = await import("vitest");
  const { replayEvents } = await import("./sse");
  const events = [
    {run_id:"r", seq:1, type:"approval_required", payload:{approval_id:"a"}},
    {run_id:"r", seq:2, type:"message", payload:{content:"已更新"}},
    {run_id:"r", seq:3, type:"done", payload:{}},
  ];
  vi.stubGlobal("fetch", async () => new Response(events.map(e=>`data: ${JSON.stringify(e)}\n\n`).join("")));
  try {
    const actual: number[] = [];
    await replayEvents("r", 0, e=>actual.push(e.seq), new AbortController().signal);
    expect(actual).toEqual([1,2,3]);
  } finally { vi.unstubAllGlobals(); }
});

it('drains durable tail events when a truncated stream is followed by a terminal status',async()=>{
 const {vi}=await import('vitest');const {replayEvents}=await import('./sse');
 const frame=(seq:number,type:string,payload:object)=>`data: ${JSON.stringify({run_id:'r',seq,type,payload})}\n\n`;
 const replies=[new Response(frame(1,'message_delta',{message_id:'m',delta:'第一段'})),Response.json({data:{status:'done',event_counter:3}}),new Response(frame(2,'message_delta',{message_id:'m',delta:'第二段'})+frame(3,'done',{}))];
 vi.stubGlobal('fetch',async()=>replies.shift()!);
 try{const actual:number[]=[];await replayEvents('r',0,e=>actual.push(e.seq),new AbortController().signal);expect(actual).toEqual([1,2,3]);}finally{vi.unstubAllGlobals()}
});
