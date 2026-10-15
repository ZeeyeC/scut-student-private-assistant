import { expect, it } from "vitest";
import { applyMessage, type ChatMessage } from "./chat-messages";

it("replays text deltas once and replaces the partial with the authoritative final message", () => {
  let messages: ChatMessage[] = [];
  const event = (seq: number, type: string, payload: Record<string, unknown>) => ({run_id: "run", seq, type, payload});
  const first = event(2, "message_delta", {message_id: "m", delta: "正在"});
  messages = applyMessage(messages, first);
  expect(messages.map(m => m.content)).toEqual(["正在"]);
  messages = applyMessage(messages, first);
  messages = applyMessage(messages, event(3, "message_delta", {message_id: "m", delta: "处理"}));
  expect(messages.map(m => m.content)).toEqual(["正在处理"]);
  messages = applyMessage(messages, event(4, "message", {message_id: "m", role: "assistant", content: "正在处理，完成。"}));
  messages = applyMessage(messages, first);
  expect(messages.map(m => m.content)).toEqual(["正在处理，完成。"]);
});
