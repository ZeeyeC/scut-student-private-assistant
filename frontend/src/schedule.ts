export type CourseInterval = {
  starts_at: string;
  ends_at: string;
  periods?: number[];
  after_period?: number;
  before_period?: number;
  protected?: boolean;
};
export type CourseIntervalsData = {
  teaching_intervals?: CourseInterval[];
  break_intervals?: CourseInterval[];
  occurrence_starts_at?: string;
  occurrence_ends_at?: string;
};
export type ScheduleEvent = CourseIntervalsData & {
  id: string;
  kind: 'course' | 'fixed_event' | 'plan_block' | 'scheduling_constraint';
  title: string;
  starts_at: string;
  ends_at: string;
  location?: string | null;
  campus?: string | null;
  course_id?: string;
  original_date?: string;
  adjusted?: boolean;
  locked?: boolean;
};
