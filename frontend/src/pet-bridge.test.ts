import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { describe, it, expect } from "vitest";

const script = readFileSync(new URL("../../campus-pet/Resources/Bridge.js", import.meta.url), "utf8");
const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };

function bridge() {
  const states: string[] = [], events: { type: string; detail?: unknown }[] = [];
  let workspaceReady = false;
  let reviewVisible = true, response = { state: "approval", review_thread_id: "older-thread" }, failed = false;
  let changed = () => {};
  const timers = new Map<number, { callback: () => unknown; delay: number }>();
  let timerId = 0;
  const listeners = new Map<string, (event: unknown) => void>();
  const window: any = {
    webkit: { messageHandlers: { petState: { postMessage: (state: string) => states.push(state) } } },
    addEventListener: (name: string, listener: (event: unknown) => void) => listeners.set(name, listener),
    dispatchEvent: (event: { type: string }) => { events.push(event); listeners.get(event.type)?.(event); return true; },
  };
  const document = {
    head: { append: () => {} }, body: { dataset: {} }, defaultView: window,
    createElement: () => ({}), addEventListener: () => {},
    querySelectorAll: () => [{ textContent: "助手", click: () => {} }],
    querySelector: (selector: string) => selector === ".workspace-shell [data-page-id]" ? (workspaceReady ? {} : null) : selector === ".review-panel" && reviewVisible ? {} : null,
  };
  runInNewContext(script, {
    window, document, AbortController,
    Event: class { constructor(public type: string) {} },
    fetch: async () => { if (failed) throw new Error("offline"); return { ok: true, status: 200, json: async () => response }; },
    CustomEvent: class { constructor(public type: string, public init: { detail?: unknown } = {}) {} get detail() { return this.init.detail; } },
    MutationObserver: class { constructor(callback: () => void) { changed = callback; } observe() {} },
    requestAnimationFrame: (callback: () => void) => callback(),
    setTimeout: (callback: () => unknown, delay: number) => { const id = ++timerId; timers.set(id, { callback, delay }); return id; },
    clearTimeout: (id: number) => timers.delete(id),
  });
  return {
    states, events, window,
    ready:()=>{workspaceReady=true;changed();},
    removeChat: () => { reviewVisible = false; changed(); },
    setState: (state: string) => { response = { ...response, state }; },
    offline: (value: boolean) => { failed = value; },
    poll: async () => {
      const timer = [...timers.entries()].sort((a, b) => a[1].delay - b[1].delay)[0];
      if (timer) { timers.delete(timer[0]); await timer[1].callback(); }
      await flush();
    },
  };
}

describe("native pet bridge", () => {
  it("keeps approval when chat DOM unmounts and returns idle after backend completion", async () => {
    const app = bridge(); await flush();
    app.removeChat(); await flush();
    expect(app.states.at(-1)).toBe("approval");
    app.setState("idle"); await app.poll();
    expect(app.states.at(-1)).toBe("idle");
  });
  it("locates pending approval in a non-default conversation without sending text to native", async () => {
    const app = bridge(); await flush();
    await app.window.__campusPet.showReview();
    expect(app.events.find(event => event.type === "campus-pet-review")?.detail).toEqual({ threadId: "older-thread" });
    expect(app.states.every(state => ["idle", "thinking", "replying", "approval", "error"].includes(state))).toBe(true);
  });
  it("shows connection errors and resynchronizes after recovery while outside chat", async () => {
    const app = bridge(); await flush(); app.removeChat(); app.offline(true);
    await app.poll(); expect(app.states.at(-1)).toBe("error");
    app.offline(false); app.setState("thinking"); await app.poll();
    expect(app.states.at(-1)).toBe("thinking");
  });
  it("queues the latest exact task before React is ready and rejects unsafe targets",async()=>{
    const app=bridge();await flush();
    expect(app.window.__campusPet.navigate({page:'tasks',taskId:'task-A'})).toBe(false);
    app.window.__campusPet.navigate({page:'tasks',taskId:'task-B'});
    for(const taskId of ['', '<script>', '../task', 'x\n', 'a'.repeat(201)])expect(app.window.__campusPet.navigate({page:'tasks',taskId})).toBe(false);
    app.ready();await flush();
    expect(app.events.filter(e=>e.type==='campus-navigate').map(e=>e.detail)).toEqual([{page:'tasks',taskId:'task-B'}]);
    expect(app.window.__campusPet.navigate('日程')).toBe(true);
    expect(app.window.__campusPet.navigate({page:'tasks',taskId:'task-B'})).toBe(true);
    expect(app.events.at(-1)?.detail).toEqual({page:'tasks',taskId:'task-B'});
  });

});
