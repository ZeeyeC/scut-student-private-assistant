import {expect,it} from "vitest";
import {formatElapsed, timerElapsed, serializeTimerAction} from "./timer-state";

it("shows confirmed time when paused or interrupted and bounded live time when connected",()=>{
  expect(formatElapsed(1500.9)).toBe("00:25:00");
  expect(timerElapsed({status:"paused",elapsed_seconds:60},1000,16000)).toBe(60);
  expect(timerElapsed({status:"interrupted",elapsed_seconds:60},1000,3601000)).toBe(60);
  expect(timerElapsed({status:"running",elapsed_seconds:60},1000,16000)).toBe(75);
});

it("serializes heartbeat and user commands for the same timer",async()=>{
  const order:string[]=[];
  let release!:()=>void;
  const gate=new Promise<void>(r=>{release=r;});
  const heartbeat=serializeTimerAction("t",async()=>{order.push("heartbeat");await gate;order.push("observed");});
  const pause=serializeTimerAction("t",async()=>{order.push("pause");});
  await Promise.resolve();
  expect(order).not.toContain("pause");
  release();await heartbeat;await pause;
  expect(order).toEqual(["heartbeat","observed","pause"]);
});
