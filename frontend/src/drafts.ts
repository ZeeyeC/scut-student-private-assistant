import type { Resource } from './types';

// Older pending plans remain in storage for inspection, but only the newest is actionable.
export function visibleDrafts(drafts: Resource[] = []) {
  const latestPlan = drafts.filter(d => d.data.draft_kind === 'plan').at(-1)?.id;
  return drafts.filter(d => d.data.draft_kind !== 'plan' || d.id === latestPlan);
}
export function navigate(page: string) {
  window.dispatchEvent(new CustomEvent('campus-navigate', {detail: page}));
}
