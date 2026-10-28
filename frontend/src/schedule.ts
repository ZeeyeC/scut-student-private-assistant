export type ScheduleEvent = {
  id: string;
  kind: 'course' | 'fixed_event' | 'plan_block' | 'scheduling_constraint';
  title: string;
  starts_at: string;
  ends_at: string;
  location?: string | null;
  course_id?: string;
  original_date?: string;
  adjusted?: boolean;
  locked?: boolean;
};
