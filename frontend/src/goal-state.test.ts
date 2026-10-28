import { expect, it } from 'vitest';
import { goalForm, goalPayload, goalOperation } from './goal-state';

it('requires an explicit budget, preserves zero and leaves unknown deadline null', () => {
  const form = goalForm();
  form.title = '学习';
  expect(() => goalPayload(0, form)).toThrow();
  form.weekly_budget_minutes = '0';
  expect(goalPayload(0, form)).toMatchObject({ revision: 0, title: '学习', deadline: null, weekly_budget_minutes: 0 });
  for (const invalid of ['-1', '1.5', '1e2', '10081']) {
    form.weekly_budget_minutes = invalid;
    expect(() => goalPayload(0, form)).toThrow();
  }
});

it('requires aware deadline and preserves stable subtask identity and task association', () => {
  const form = goalForm();
  Object.assign(form, { title: '锻炼', weekly_budget_minutes: '60', deadline: '2026-12-01T12:00:00', subtasks: [{ id: 'sub-1', title: '跑步', status: 'completed', estimated_minutes: '30', task_id: 'task-1' }] });
  expect(() => goalPayload(1, form)).toThrow();
  form.deadline = '2026-12-01T12:00:00+08:00';
  expect(goalPayload(1, form).subtasks).toEqual([{ id: 'sub-1', title: '跑步', status: 'completed', estimated_minutes: 30, task_id: 'task-1' }]);
  form.subtasks[0].estimated_minutes = '';
  expect(() => goalPayload(1, form)).toThrow();
});

it('keeps the exact mutation and idempotency key for a lost response retry', () => {
  const form = goalForm();
  Object.assign(form, { title: '学习', weekly_budget_minutes: '60' });
  const body = goalPayload(0, form);
  const op = goalOperation('/goals', 'POST', body);
  body.title = 'changed';
  expect(op.body.title).toBe('学习');
  expect(op.idempotencyKey).toBeTruthy();
  expect(goalOperation('/goals', 'POST', body).idempotencyKey).not.toBe(op.idempotencyKey);
});
