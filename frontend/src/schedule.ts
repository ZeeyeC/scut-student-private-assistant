export type ScheduleEvent = {
  id: string;
  kind: 'course' | 'fixed_event' | 'plan_block';
  title: string;
  starts_at: string;
  ends_at: string;
  location?: string | null;
  locked?: boolean;
};
