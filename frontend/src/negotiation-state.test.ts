import { describe, it, expect } from "vitest";
import { emptyIntentForm, intentConditions, intentForm, negotiationOperation, selectIntentId } from "./negotiation-state";

describe("explicit negotiation state", () => {
  it("does not turn missing dates or periods into assumed habits", () => {
    const form = emptyIntentForm();
    expect(form.target_date).toBe("");
    expect(form.protected_intervals).toEqual([]);
    expect(() => intentConditions(form, "Asia/Shanghai")).toThrow();
    const data = intentConditions({...form, description:"保留复习",target_date:"2030-12-30"},"Asia/Shanghai");
    expect(data.reduced_daily_limit_minutes).toBeNull();
    expect(data.preferred_intervals).toEqual([]);
  });
  it("freezes request payload and operation key for an unknown response", () => {
    const body = {revision:2,source_revision:4,option_id:"preferred"};
    const operation = negotiationOperation("/planning-intents/one/choose","POST",body);
    body.revision=99;
    const restored = JSON.parse(JSON.stringify(operation));
    expect(restored.body.revision).toBe(2);
    expect(restored.idempotencyKey).toBe(operation.idempotencyKey);
  });
  it("restores only an ID present in this owner's fetched intents", () => {
    expect(selectIntentId([{id:"a"},{id:"b"}],"a")).toBe("a");
    expect(selectIntentId([{id:"a"},{id:"b"}],"other-owner")).toBe("b");
    expect(selectIntentId([],"a")).toBe("new");
  });
  it("uses the settings IANA zone for datetime-local intervals and restores local fields", () => {
    const form={...emptyIntentForm(), description:"跨年复习", target_date:"2030-12-31", preferred_intervals:[{starts_at:"2030-12-31T14:00",ends_at:"2030-12-31T15:00"}]};
    const data=intentConditions(form,"Asia/Shanghai");
    expect(Date.parse(data.preferred_intervals[0].starts_at)).toBe(Date.parse("2030-12-31T06:00:00Z"));
    expect(intentForm(data).preferred_intervals).toEqual(form.preferred_intervals);
    const america=intentConditions(form,"America/New_York");
    expect(Date.parse(america.preferred_intervals[0].starts_at)).toBe(Date.parse("2030-12-31T19:00:00Z"));
  });
  it("asks for another explicit clock time across DST gaps or folds", () => {
    const form={...emptyIntentForm(),description:"复习",target_date:"2026-03-08",protected_intervals:[{starts_at:"2026-03-08T02:30",ends_at:"2026-03-08T04:00"}]};
    expect(()=>intentConditions(form,"America/New_York")).toThrow("跳过");
    expect(()=>intentConditions({...form,target_date:"2026-11-01",protected_intervals:[{starts_at:"2026-11-01T01:30",ends_at:"2026-11-01T03:00"}]},"America/New_York")).toThrow("两个同名时间");
  });
});
