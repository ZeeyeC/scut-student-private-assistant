import AppKit

@main
struct NativeTests {
    static func main() {
        MainActor.assumeIsolated {
            _ = NSApplication.shared
            runBrowserLaunchPolicyTests()
            runWorkspaceWindowTests()
            runPetTodoPanelTests()
            runPetAssetTests()
            let date = ScheduleReminder.parseDate("2026-10-18T00:30:00+08:00")!
            func task(_ id: String, _ status: String = "open") -> [String: Any] {
                ["id":id, "revision":1, "data":["title":id,"status":status,"due_at":"2026-10-18T18:00:00+08:00"]]
            }
            func block(_ id: String, _ start: String, _ end: String, _ status: String = "suggested") -> [String: Any] {
                ["data":["task_id":id,"starts_at":start,"ends_at":end,"status":status]]
            }
            let tasks = [task("today"),task("tomorrow"),task("due-only"),task("done","completed"),task("archived","archived"),task("spent"),task("overnight"),task("boundary")]
            let blocks = [
                block("today","2026-10-17T17:00:00Z","2026-10-17T18:00:00Z"),
                block("today","2026-10-18T15:00:00+08:00","2026-10-18T16:00:00+08:00"),
                block("tomorrow","2026-10-19T09:00:00+08:00","2026-10-19T10:00:00+08:00"),
                block("done","2026-10-18T09:00:00+08:00","2026-10-18T10:00:00+08:00"),
                block("archived","2026-10-18T09:00:00+08:00","2026-10-18T10:00:00+08:00"),
                block("spent","2026-10-18T09:00:00+08:00","2026-10-18T10:00:00+08:00","completed"),
                block("overnight","2026-10-17T23:30:00+08:00","2026-10-18T00:30:00+08:00"),
                block("boundary","2026-10-17T23:00:00+08:00","2026-10-18T00:00:00+08:00"),
            ]
            let today = PetScheduledTask.today(tasks: tasks, blocks: blocks, timezone: "Asia/Shanghai", now: date)
            precondition(today.map(\.id) == ["overnight","today"], "Only open tasks with an unfinished block overlapping the configured local day")
            precondition(today[1].blocks.count == 2, "Multiple blocks must share one bubble")
            let tomorrow = PetScheduledTask.today(tasks: tasks, blocks: blocks, timezone: "Asia/Shanghai", now: date.addingTimeInterval(86400))
            precondition(tomorrow.map(\.id) == ["tomorrow"], "Rollover must not retain yesterday's tasks")
            let app = AppDelegate()
            app.pet.mood = .approval
            app.toggleSleep()
            precondition(app.pet.mood == .sleeping, "Pause must show sleeping")
            app.toggleSleep()
            precondition(app.pet.mood == .approval, "Resume must retain pending approval")
            for incoming in [PetMood.replying, .approval, .idle] {
                app.toggleSleep()
                app.receiveAssistantMood(incoming)
                precondition(app.pet.mood == .sleeping, "Incoming state must not resume paused animation")
                app.toggleSleep()
                precondition(app.pet.mood == incoming, "Resume must use the state received while paused")
            }
            let menu = app.petMenu()
            guard let exits = menu.item(withTitle: "关闭与退出")?.submenu else { preconditionFailure("Pet must expose an exit submenu") }
            precondition(exits.item(withTitle: "仅退出桌宠（后台继续运行）")?.action == #selector(AppDelegate.quit), "Pet-only exit must keep existing quit behavior")
            precondition(exits.item(withTitle: "停止后台并退出…") != nil, "Service shutdown must be separately selectable")
            let identity: [String: Any] = ["application": "campus-companion", "mode": "local", "desktop_protocol": 1]
            precondition(AppDelegate.pages == ["今日", "日程", "任务", "助手", "设置"], "Native navigation follows the App workspace")
            precondition(AppDelegate.displayPage("目标与复盘") == "任务", "Legacy goals entry still reaches the task subview")
            precondition(AppDelegate.displayPage("课表") == "日程")
            precondition(AppDelegate.displayPage("作业") == "任务")
            let capabilities = ["after-class-checkin", "calendar-course-entry", "pet-state", "schedule-reminders", "planning-constraints-once", "timetable-recognition", "timetable-text", "planning-today", "course-changes", "execution-timers-v1", "profiles-v1", "goals-v1", "weekly-review-v1", "planning-core-v1", "b-interaction-v1", "project-completion-v1", "desktop-workspace-v1", "desktop-import-bridge-v1"]
            func rejects(_ body: [String: Any], status: Int = 200) -> Bool {
                do { try ServiceController.validateHealth(status: status, body: body); return false }
                catch { return true }
            }
            precondition(rejects(identity), "demo1.1 health must be recognized as incompatible")
            for missing in capabilities {
                precondition(rejects(identity.merging(["capabilities": capabilities.filter { $0 != missing }]) { _, new in new }), "Missing capability must block loading old UI")
            }
            let compatible = identity.merging(["capabilities": capabilities]) { _, new in new }
            precondition(!rejects(compatible), "Compatible shared backend must be reusable")
            precondition(rejects(compatible, status: 503))
            precondition(rejects(compatible.merging(["application": "other"]) { _, new in new }))
            precondition(rejects(compatible.merging(["mode": "shared"]) { _, new in new }))
            precondition((try? LocalHealthTransport.healthURL(for: URL(string: "http://127.0.0.1:5189")!))?.absoluteString == "http://127.0.0.1:5189/api/healthz")
            for origin in ["https://127.0.0.1:5189", "http://localhost:5189", "http://127.0.0.1.example.com:5189", "http://192.0.2.1:5189", "http://127.0.0.1:80", "http://user:pass@127.0.0.1:5189", "http://127.0.0.1:5189/other", "http://127.0.0.1:5189?q=1", "http://127.0.0.1:5189/#fragment"] {
                precondition((try? LocalHealthTransport.healthURL(for: URL(string: origin)!)) == nil, "Health must refuse non-loopback, credentials, untrusted ports and alternate paths before networking")
            }
            let reminder: [String: Any] = ["key":"test", "title":"阅读", "starts_at":"2026-10-17T20:00:00.123456+08:00", "target_kind":"website", "target":"https://example.com/work"]
            precondition(ScheduleReminder(reminder)?.destination?.host == "example.com")
            precondition(ScheduleReminder(reminder.merging(["target":"javascript:alert(1)"]) { _, new in new })?.destination == nil)
            let file = reminder.merging(["target_kind":"file", "target":"/tmp/中文作业.pdf"]) { _, new in new }
            precondition(ScheduleReminder(file)?.destination?.path == "/tmp/中文作业.pdf")
            precondition(ScheduleReminder(file.merging(["target":"relative.pdf"]) { _, new in new })?.destination == nil)
            let purple = PetView.reminderColor(NSColor.yellow).usingColorSpace(.deviceRGB)!
            precondition(purple.blueComponent > purple.greenComponent, "Yellow must become purple")
            let cream = NSColor(deviceRed: 0.95, green: 0.93, blue: 0.9, alpha: 1)
            precondition(PetView.reminderColor(cream) == cream, "Keep the pale belly unchanged")
            print("Native regression checks passed")
        }
    }
}
