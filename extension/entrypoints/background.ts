import { browser } from "wxt/browser";
import { appOrigin, adapter } from "../lib/build-config";
import { onMessage, type Binding, type BridgeEvent } from "../lib/protocol";
import { serialQueue } from "../lib/serial";
export default defineBackground(() => {
  const queue = serialQueue();
  const load = async () =>
    ((await browser.storage.session.get("bindings")).bindings ?? {}) as Record<
      string,
      Binding
    >;
  const save = async (b: Record<string, Binding>) =>
    browser.storage.session.set({ bindings: b });
  const check = (sender: {
    tab?: { id?: number; url?: string };
    frameId?: number;
  }) => {
    if (
      sender.frameId !== 0 ||
      !sender.tab?.id ||
      !sender.tab.url ||
      new URL(sender.tab.url).origin !== appOrigin
    )
      throw new Error("非法助手消息来源");
    return sender.tab.id;
  };
  // A portal may open the timetable in a child tab. Only a real opener
  // chain rooted in this import can inherit it; other school tabs stay private.
  const schoolBinding = async (
    bindings: Record<string, Binding>,
    tabId: number,
    url: string,
  ) => {
    if (!adapter || new URL(url).origin !== adapter.school_origin) return null;
    const live = Object.values(bindings).filter(
      (b) => Date.parse(b.expiresAt) > Date.now(),
    );
    const direct = live.find((b) => b.schoolTab === tabId);
    if (direct) return direct;
    if (
      !adapter.route_pattern ||
      !new RegExp(adapter.route_pattern).test(new URL(url).pathname)
    )
      return null;
    const visited = new Set<number>([tabId]);
    let current = tabId;
    for (let depth = 0; depth < 16; depth++) {
      let tab;
      try {
        tab = await browser.tabs.get(current);
      } catch {
        return null;
      }
      if (!tab.url || new URL(tab.url).origin !== adapter.school_origin) return null;
      const opener = tab.openerTabId;
      if (opener === undefined || visited.has(opener)) return null;
      const binding = live.find((b) =>
        (b.schoolTabs ?? [b.schoolTab]).includes(opener),
      );
      if (binding) {
        binding.schoolTabs = [
          ...new Set([...(binding.schoolTabs ?? [binding.schoolTab]), tabId]),
        ];
        binding.schoolTab = tabId;
        await save(bindings);
        return binding;
      }
      visited.add(opener);
      current = opener;
    }
    return null;
  };
  onMessage("start", ({ data, sender }) => {
    return queue(async () => {
      const appTab = check(sender);
      if (!adapter)
        throw new Error("external_input_required：华工适配尚未核验");
      if (
        !/^[a-f0-9-]{36}$/.test(data.sessionId) ||
        Date.parse(data.expiresAt) <= Date.now()
      )
        throw new Error("导入会话无效");
      const bindings = await load();
      const existing = bindings[data.sessionId];
      if (existing) {
        if (existing.owner !== data.owner) throw new Error("账号不符");
        existing.appTab = appTab;
        existing.nonce = data.nonce;
        existing.bindingGeneration = data.bindingGeneration;
        await save(bindings);
        const tab = await browser.tabs.update(existing.schoolTab, {
          active: true,
        });
        if (tab?.windowId)
          await browser.windows.update(tab.windowId, { focused: true });
        return existing;
      }
      // Persist association immediately after the browser returns the real tab id.
      const tab = await browser.tabs.create({
        url: adapter.entry_url,
        active: true,
      });
      if (!tab.id) throw new Error("浏览器未返回标签页");
      if (tab.windowId)
        await browser.windows.update(tab.windowId, { focused: true });
      const b: Binding = {
        sessionId: data.sessionId,
        appTab,
        schoolTab: tab.id,
        schoolTabs: [tab.id],
        nonce: data.nonce,
        bindingGeneration: data.bindingGeneration,
        owner: data.owner,
        expiresAt: data.expiresAt,
        events: [{ kind: "opened", event_id: crypto.randomUUID() }],
      };
      bindings[data.sessionId] = b;
      await save(bindings);
      await browser.alarms.create(data.sessionId, {
        when: Date.parse(data.expiresAt),
      });
      return b;
    });
  });
  onMessage("restore", ({ data, sender }) =>
    queue(async () => {
      const appTab = check(sender),
        bindings = await load(),
        b = bindings[data.sessionId];
      if (!b || b.owner !== data.owner || b.bindingGeneration !== data.bindingGeneration || Date.parse(b.expiresAt) <= Date.now())
        return null;
      b.appTab = appTab;
      b.nonce = data.nonce;
      await save(bindings);
      return b;
    }),
  );
  onMessage("stop", ({ data, sender }) =>
    queue(async () => {
      check(sender);
      const bindings = await load();
      if (bindings[data.sessionId]?.owner === data.owner && bindings[data.sessionId]?.bindingGeneration === data.bindingGeneration) {
        delete bindings[data.sessionId];
        await save(bindings);
        await browser.alarms.clear(data.sessionId);
      }
    }),
  );
  onMessage("binding", ({ sender }) =>
    queue(async () => {
      if (
        !adapter ||
        !sender.tab?.url ||
        new URL(sender.tab.url).origin !== adapter.school_origin ||
        sender.frameId !== 0
      )
        return null;
      if (sender.tab.id === undefined) return null;
      return schoolBinding(await load(), sender.tab.id, sender.tab.url);
    }),
  );
  onMessage("school", ({ data, sender }) =>
    queue(async () => {
      if (
        !adapter ||
        sender.frameId !== 0 ||
        !sender.tab?.url ||
        new URL(sender.tab.url).origin !== adapter.school_origin
      )
        throw new Error("非法学校来源");
      const bindings = await load(),
        b = sender.tab.id === undefined
          ? null
          : await schoolBinding(bindings, sender.tab.id, sender.tab.url);
      if (!b || Date.parse(b.expiresAt) <= Date.now())
        throw new Error("无关联导入");
      if (data.kind === "capture") {
        if (
          !data.fragments?.length ||
          !data.semester_label ||
          data.fragments.some(
            (f) => new TextEncoder().encode(f).length > 1048576,
          )
        )
          throw new Error("捕获无效");
        b.capture = {
          fragments: data.fragments,
          semester_label: data.semester_label,
        };
        b.captured = true;
      } else if (!b.events.some((e) => e.kind === data.kind))
        b.events.push({
          kind: data.kind as BridgeEvent["kind"],
          event_id: crypto.randomUUID(),
          error_code: data.error_code,
        });
      await save(bindings);
      if (data.kind === "capture")
        try {
          await browser.tabs.update(b.appTab, { active: true });
        } catch {
          /* app tab may be closed; storage permits rebind */
        }
    }),
  );
  browser.tabs.onRemoved.addListener((id) => {
    void queue(async () => {
      const bindings = await load();
      for (const b of Object.values(bindings)) {
        if (b.schoolTab === id)
          b.events.push({
            kind: "failed",
            event_id: crypto.randomUUID(),
            error_code: "school_tab_closed",
          });
      }
      await save(bindings);
    });
  });
  browser.alarms.onAlarm.addListener((a) => {
    void queue(async () => {
      const bindings = await load();
      delete bindings[a.name];
      await save(bindings);
    });
  });
});
