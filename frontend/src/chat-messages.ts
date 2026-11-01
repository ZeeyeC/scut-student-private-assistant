import type { PublicEvent } from "./sse";
export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  seq: number;
  asset_id?: string;
  asset_ids?: string[];
  source_ids?: string[];
};

export function messageAssetIds(source?: {
  asset_ids?: unknown;
  asset_id?: unknown;
}): string[] {
  if (!source) return [];
  const list: string[] = [];
  if (Array.isArray(source.asset_ids)) {
    for (const item of source.asset_ids) {
      if (typeof item === "string" && item.length > 0 && !list.includes(item)) {
        list.push(item);
      }
    }
  }
  if (
    typeof source.asset_id === "string" &&
    source.asset_id.length > 0 &&
    !list.includes(source.asset_id)
  ) {
    list.push(source.asset_id);
  }
  return list;
}

export function applyMessage(messages: ChatMessage[], event: PublicEvent): ChatMessage[] {
  if (event.type !== "message" && event.type !== "message_delta") return messages;
  const p = event.payload, index = messages.findIndex(m => m.id === p.message_id);
  const previous = index < 0 ? undefined : messages[index];
  if (previous && event.seq <= previous.seq) return messages;
  const nextIds = messageAssetIds(p);
  const assetIds = nextIds.length > 0 ? nextIds : messageAssetIds(previous);
  const message: ChatMessage = {
    id: p.message_id,
    role: event.type === "message_delta" ? "assistant" : p.role,
    content: event.type === "message_delta" ? (previous?.content ?? "") + p.delta : p.content,
    seq: event.seq,
    source_ids: Array.isArray(p.source_ids)?p.source_ids:previous?.source_ids,
    ...(assetIds.length > 0 ? { asset_ids: assetIds, asset_id: assetIds[0] } : {}),
  };
  return index < 0 ? [...messages, message] : messages.map((m, i) => i === index ? message : m);
}
