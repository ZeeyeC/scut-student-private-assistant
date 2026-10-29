import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "e2e", testMatch: ["after-class-recovery.spec.ts", "pet-review.spec.ts", "schedule-reminders.spec.ts", "timetable-schedule.spec.ts", "scheduling-constraints.spec.ts", "timetable-recognition.spec.ts", "timetable-text.spec.ts", "today-plan.spec.ts", "course-changes.spec.ts", "execution-feedback.spec.ts", "independent-features.spec.ts"], workers: 1,
  timeout: 30000, expect: { timeout: 5000 },
  use: { baseURL: "http://127.0.0.1:5290", channel: process.env.PET_BROWSER_CHANNEL === "bundled" ? undefined : "chrome", trace: "retain-on-failure" },
  webServer: {
    command: "../backend/.venv/bin/python -m uvicorn tests.pet_e2e_server:app --app-dir ../backend --host 127.0.0.1 --port 5290",
    url: "http://127.0.0.1:5290/api/healthz", reuseExistingServer: false,
  },
});
