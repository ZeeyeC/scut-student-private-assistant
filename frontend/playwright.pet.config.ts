import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "e2e", testMatch: ["chat-run-race.spec.ts", "pet-todo-renderer.spec.ts", "ui-refinement.spec.ts", "ui-refinement.visual.spec.ts", "timetable-import-layout.spec.ts", "app-school-import.spec.ts", "app-workspace.spec.ts", "project-completion.spec.ts", "semester-calendar.spec.ts", "person-a-delivery.spec.ts", "b-interaction.spec.ts", "after-class-recovery.spec.ts", "pet-review.spec.ts", "schedule-reminders.spec.ts", "timetable-schedule.spec.ts", "scheduling-constraints.spec.ts", "timetable-recognition.spec.ts", "timetable-text.spec.ts", "today-plan.spec.ts", "course-changes.spec.ts", "execution-feedback.spec.ts", "independent-features.spec.ts", "course-intervals.spec.ts", "conflicts.spec.ts", "planning-capacity.spec.ts", "replanning.spec.ts", "planning-workbench.spec.ts"], workers: 1,
  timeout: 30000, expect: { timeout: 5000 },
  use: { baseURL: "http://127.0.0.1:5290", channel: process.env.PET_BROWSER_CHANNEL === "bundled" ? undefined : "chrome", trace: "retain-on-failure" },
  webServer: {
    command: "../backend/.venv/bin/python -m uvicorn tests.pet_e2e_server:app --app-dir ../backend --host 127.0.0.1 --port 5290",
    url: "http://127.0.0.1:5290/api/healthz", reuseExistingServer: false,
  },
});
