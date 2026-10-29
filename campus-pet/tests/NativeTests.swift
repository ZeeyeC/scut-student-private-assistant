import AppKit

@main
struct NativeTests {
    static func main() {
        MainActor.assumeIsolated {
            _ = NSApplication.shared
            for screen in [NSRect(x: 0, y: 0, width: 1200, height: 800), NSRect(x: -1200, y: 200, width: 1200, height: 800)] {
                for x in [screen.minX, screen.midX - 95, screen.maxX - 190] {
                    for y in [screen.minY, screen.midY - 105, screen.maxY - 210] {
                        let pet = NSRect(x: x, y: y, width: 190, height: 210)
                        let bubbles = PetTaskRingLayout.frames(near: pet, within: screen)
                        precondition(bubbles.count == 6, "Six bubbles must fit even at display corners")
                        for (index, bubble) in bubbles.enumerated() {
                            precondition(screen.contains(bubble), "Bubbles must stay on their display")
                            precondition(!pet.intersects(bubble), "Leave the pet clickable")
                            for other in bubbles.dropFirst(index + 1) { precondition(!bubble.intersects(other)) }
                        }
                    }
                }
            }
            let slots = PetTaskRingLayout.slots([], tasks: (1...8).map(String.init), capacity: 6)
            precondition(slots == (1...6).map { String($0) })
            let filled = PetTaskRingLayout.slots(slots, tasks: ["1","2","4","5","6","7","8"], capacity: 6)
            precondition(filled == ["1","2","7","4","5","6"], "Only the completed slot should change")
            precondition(PetScheduledTask.abbreviation("完成高数作业") == "高数")
            precondition(PetScheduledTask.abbreviation("阅读论文") == "论文")
            precondition(PetScheduledTask.abbreviation("题") == "题")
            precondition(PetScheduledTask.abbreviation(" ! ") == "待办")
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
            let button = PetTaskBubbleButton(frame: NSRect(x: 0, y: 0, width: 54, height: 54))
            precondition(button.containsCircle(NSPoint(x: 27, y: 27)))
            precondition(!button.containsCircle(NSPoint(x: 1, y: 1)), "Transparent circle corners must pass through")
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
            precondition(AppDelegate.pages[4] == "目标与复盘", "Compact desktop must expose goals and weekly review")
            precondition(AppDelegate.pages.last == "设置", "Adding goals must preserve settings navigation")
            let capabilities = ["after-class-checkin", "calendar-course-entry", "pet-state", "schedule-reminders", "planning-constraints-once", "timetable-recognition", "timetable-text", "planning-today", "course-changes", "execution-timers-v1", "profiles-v1", "goals-v1", "weekly-review-v1", "planning-core-v1", "b-interaction-v1"]
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
