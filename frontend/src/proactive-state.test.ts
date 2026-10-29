import { describe, expect, it } from 'vitest';
import { proactivePreferencePayload, proactiveOperation, proactiveActionOperation, visibleProactive, type ProactivePreferences, type ProactiveSuggestion } from './proactive-state';
const preferences:ProactivePreferences={enabled:false,categories:{deadline:true,capacity:true,unknown_estimate:true,available_window:true,facts_changed:true},timezone:null,quiet_hours:null};
const item={id:'suggestion',kind:'proactive_suggestion',revision:2,data:{category:'deadline',fingerprint:'a'.repeat(64),state:'pending',visible:true}} as ProactiveSuggestion;

describe('silent proactive controls',()=>{
  it('preserves unknown quiet hours and never invents sleep or a timezone',()=>{
    const payload=proactivePreferencePayload(0,preferences);
    expect(payload.data.enabled).toBe(false);
    expect(payload.data.timezone).toBeNull();expect(payload.data.quiet_hours).toBeNull();
    const explicit=proactivePreferencePayload(1,{...preferences,quiet_hours:[]});
    expect(explicit.data.quiet_hours).toEqual([]);
  });
  it('accepts explicitly zoned overnight hours with starting weekdays',()=>{
    const payload=proactivePreferencePayload(1,{...preferences,timezone:'America/New_York',quiet_hours:[{weekdays:[7],start:'22:00',end:'02:00'}]});
    expect(payload.data.quiet_hours?.[0].end).toBe('02:00');
  });
  it.each([
    {timezone:'Bad/Zone'},
    {quiet_hours:[{weekdays:[1],start:'22:00',end:'07:00'}]},
    {timezone:'Asia/Shanghai',quiet_hours:[{weekdays:[0],start:'22:00',end:'07:00'}]},
    {timezone:'Asia/Shanghai',quiet_hours:[{weekdays:[1],start:'22:00',end:'22:00'}]},
  ])('rejects invalid explicit quiet preferences %j',patch=>{
    expect(()=>proactivePreferencePayload(1,{...preferences,...patch})).toThrow();
  });
  it('freezes exact revision, fingerprint and idempotency key for a lost-response retry',()=>{
    const operation=proactiveActionOperation(item,'snooze',{snooze_minutes:30});
    const clone=structuredClone(operation);
    item.revision=9;
    expect(operation.body).toEqual({revision:2,fingerprint:'a'.repeat(64),action:'snooze',snooze_minutes:30});
    expect(operation).toEqual(clone);
    const settings=proactiveOperation('PUT','/proactive/preferences',{revision:1,data:preferences});
    preferences.categories.deadline=false;
    expect((settings.body.data as ProactivePreferences).categories.deadline).toBe(true);
    preferences.categories.deadline=true;
  });
  it('requires explicit confirmation mode and duration and guards inactive display',()=>{
    expect(()=>proactiveActionOperation(item,'snooze',{snooze_minutes:0})).toThrow();
    expect(()=>proactiveActionOperation(item,'accept')).toThrow();
    expect(visibleProactive([item],true)).toHaveLength(1);
    expect(visibleProactive([item],false)).toEqual([]);
  });
});
