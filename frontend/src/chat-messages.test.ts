import { expect, it } from "vitest";
import { applyMessage, messageAssetIds, type ChatMessage } from "./chat-messages";

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

it("preserves ordered multi-image asset_ids and falls back to legacy asset_id without duplicates", () => {
  let messages: ChatMessage[] = [];
  const event = (seq: number, type: string, payload: Record<string, unknown>) => ({run_id: "run", seq, type, payload});

  messages = applyMessage(messages, event(1, "message", {
    message_id: "u1",
    role: "user",
    content: "识别这两张图",
    asset_ids: ["asset-1", "asset-2"],
    asset_id: "asset-1",
  }));
  expect(messages[0].asset_ids).toEqual(["asset-1", "asset-2"]);
  expect(messages[0].asset_id).toEqual("asset-1");
  expect(messageAssetIds(messages[0])).toEqual(["asset-1", "asset-2"]);

  messages = applyMessage(messages, event(2, "message", {
    message_id: "u2",
    role: "user",
    content: "旧版单图记录",
    asset_id: "legacy-only",
  }));
  expect(messages[1].asset_ids).toEqual(["legacy-only"]);
  expect(messages[1].asset_id).toEqual("legacy-only");
  expect(messageAssetIds(messages[1])).toEqual(["legacy-only"]);
});
