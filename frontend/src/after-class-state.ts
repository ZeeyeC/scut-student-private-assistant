export type Item = { content: string; estimated_minutes: number; due_at: string };
export type Answer = { course_key: string; status: "pending" | "none" | "homework"; items: Item[] };
type StoredAnswer = Omit<Answer, "items"> & { items: (Omit<Item, "due_at"> & { due_at: string | null })[] };

export const newItem = (): Item => ({ content: "", estimated_minutes: 45, due_at: "" });
const toInput = (value: string) => {
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};
export const itemPayload = (item: Item) => ({ ...item, due_at: item.due_at ? new Date(item.due_at).toISOString() : null });

export function mergePendingAnswers(courses: { key: string }[], serverDraft: StoredAnswer[], localAnswers: Answer[]): Answer[] {
  return courses.map(course => {
    const local = localAnswers.find(answer => answer.course_key === course.key);
    if (local) return local;
    const stored = serverDraft.find(answer => answer.course_key === course.key);
    return {
      course_key: course.key, status: stored?.status ?? "pending",
      items: stored?.items.length ? stored.items.map(item => ({ ...item, due_at: item.due_at ? toInput(item.due_at) : "" })) : [newItem()],
    };
  });
}

export function draftAnswers(answers: Answer[]) {
  return answers.map(answer => ({ ...answer, items: answer.status === "homework" ? answer.items.map(itemPayload) : [] }));
}
