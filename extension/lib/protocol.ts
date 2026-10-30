import { defineExtensionMessaging } from "@webext-core/messaging";
export type Binding = {
  sessionId: string;
  bindingGeneration?: string;
  appTab: number;
  schoolTab: number;
  schoolTabs?: number[];
  nonce: string;
  owner: string;
  expiresAt: string;
  events: BridgeEvent[];
  capture?: { fragments: string[]; semester_label: string };
  captured?: boolean;
};
export type BridgeEvent = {
  event_id: string;
  kind: "opened" | "waiting_timetable" | "extracting" | "failed";
  error_code?: string;
};
type Protocol = {
  start(data: {
    sessionId: string;
    bindingGeneration?: string;
    nonce: string;
    owner: string;
    expiresAt: string;
  }): Promise<Binding>;
  restore(data: {
    sessionId: string;
    bindingGeneration?: string;
    nonce: string;
    owner: string;
  }): Promise<Binding | null>;
  stop(data: { sessionId: string; owner: string; bindingGeneration?: string }): Promise<void>;
  school(data: {
    kind: "waiting_timetable" | "extracting" | "failed" | "capture";
    fragments?: string[];
    semester_label?: string;
    error_code?: string;
  }): Promise<void>;
  binding(): Promise<Binding | null>;
};
export const { sendMessage, onMessage } = defineExtensionMessaging<Protocol>();
