import { describe, expect, it } from 'vitest';
import { navigationFromEvent, nextNavigation } from './navigation';

describe('App navigation', () => {
  it('maps legacy entries into the four pages and preserves the subview', () => {
    expect(navigationFromEvent('campus-navigate', '作业')).toEqual({page:'tasks'});
    expect(navigationFromEvent('campus-navigate', '目标与复盘')).toEqual({page:'tasks',taskTab:'goals'});
    expect(navigationFromEvent('campus-navigate', '课表')).toEqual({page:'calendar',calendarFilter:'courses'});
    expect(navigationFromEvent('campus-navigate', '今日')).toEqual({page:'today'});
  });
  it('locates saved learning arrangements and timetable reminders on the same calendar', () => {
    const date='2026-10-30T10:00:00+08:00';
    expect(navigationFromEvent('campus-calendar-saved', date)).toEqual({page:'calendar',focusDate:date,calendarFilter:'all'});
    expect(navigationFromEvent('campus-timetable-focus', date)).toEqual({page:'calendar',focusDate:date,calendarFilter:'courses'});
  });
  it('retains the exact approval thread on repeated requests', () => {
    const target=navigationFromEvent('campus-pet-review',{threadId:'thread-7'})!;
    expect(target).toEqual({page:'assistant',threadId:'thread-7'});
    const first=nextNavigation({page:'today',request:0},target);
    expect(nextNavigation(first,target)).toEqual({...target,request:2});
  });
  it('preserves a task identifier when native suggestions locate a task', () => {
    expect(navigationFromEvent('campus-navigate',{page:'tasks',taskId:'task-2',taskTab:'todo'})).toEqual({page:'tasks',taskId:'task-2',taskTab:'todo'});
  });
  it('resets an old focus when the user chooses another page', () => {
    expect(nextNavigation({page:'assistant',threadId:'old',request:9},{page:'calendar'})).toEqual({page:'calendar',request:10});
  });
  it.each([
    ['campus-navigate','unknown'],['campus-navigate',null],
    ['campus-navigate',{page:'settings',threadId:'wrong-page'}],
    ['campus-navigate',{page:'tasks',taskId:42}],
    ['campus-navigate',{page:'tasks',taskTab:'unknown'}],
    ['campus-calendar-saved','not a date'],
    ['campus-timetable-focus','2026-02-31'],
    ['campus-pet-review',{threadId:42}],['other','今日'],
  ])('rejects an invalid target: %s %j', (event,detail) => {
    expect(navigationFromEvent(event,detail)).toBeNull();
  });
});
