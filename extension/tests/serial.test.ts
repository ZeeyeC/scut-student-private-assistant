import { expect, it } from "vitest";
import { serialQueue } from "../lib/serial";

it("capture and GUI restore cannot lose each other and stop cannot be resurrected", async () => {
  const run = serialQueue();
  let state: { nonce: string; capture?: string } | null = { nonce: "old" };
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const capture = run(async () => {
    const snapshot = { ...state! };
    await gate;
    state = { ...snapshot, capture: "table" };
  });
  const restore = run(async () => {
    const snapshot = { ...state! };
    state = { ...snapshot, nonce: "new" };
  });
  release();
  await Promise.all([capture, restore]);
  expect(state).toEqual({ nonce: "new", capture: "table" });
  const stop = run(async () => {
    state = null;
  });
  const late = run(async () => {
    if (state) state = { ...state, capture: "late" };
  });
  await Promise.all([stop, late]);
  expect(state).toBeNull();
  await expect(
    run(async () => {
      throw new Error("bad event");
    }),
  ).rejects.toThrow();
  expect(await run(async () => 42)).toBe(42);
});
