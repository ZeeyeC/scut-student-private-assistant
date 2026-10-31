import type { PublicEvent } from "./sse";
export type ChatMessage = {id: string; role: "user" | "assistant"; content: string; seq: number; asset_id?:string};

export function applyMessage(messages: ChatMessage[], event: PublicEvent): ChatMessage[] {
  if (event.type !== "message" && event.type !== "message_delta") return messages;
  const p = event.payload, index = messages.findIndex(m => m.id === p.message_id);
  const previous = index < 0 ? undefined : messages[index];
  if (previous && event.seq <= previous.seq) return messages;
  const message: ChatMessage = {
    id: p.message_id,
    role: event.type === "message_delta" ? "assistant" : p.role,
    content: event.type === "message_delta" ? (previous?.content ?? "") + p.delta : p.content,
    seq: event.seq,
    ...(p.asset_id?{asset_id:p.asset_id}:previous?.asset_id?{asset_id:previous.asset_id}:{}),
  };
  return index < 0 ? [...messages, message] : messages.map((m, i) => i === index ? message : m);
}
