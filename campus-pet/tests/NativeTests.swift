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
            app.installMenus()
            let appSubmenu = NSApp.mainMenu?.items.first?.submenu
            let cmdQItem = appSubmenu?.items.first(where: { $0.keyEquivalent == "q" })
            precondition(cmdQItem?.action == #selector(AppDelegate.normalQuit), "Cmd+Q must invoke normalQuit so applicationShouldTerminate stops the backend")
            let suiteName = "CampusPetLifecycleTests.\(UUID().uuidString)"
            let testDefaults = UserDefaults(suiteName: suiteName)!
            defer { testDefaults.removePersistentDomain(forName: suiteName) }
            let tempRoot = FileManager.default.temporaryDirectory.appendingPathComponent("campus-pet-profile-\(UUID().uuidString)", isDirectory: true)
            let rememberedDir = tempRoot.appendingPathComponent("remembered", isDirectory: true)
            let explicitDir = tempRoot.appendingPathComponent("explicit", isDirectory: true)
            try! FileManager.default.createDirectory(at: rememberedDir, withIntermediateDirectories: true)
            try! FileManager.default.createDirectory(at: explicitDir, withIntermediateDirectories: true)
            defer { try? FileManager.default.removeItem(at: tempRoot) }
            let withoutRemember = LaunchOptions.parse(args: ["CampusPet", "--data-dir", explicitDir.path], defaults: testDefaults)
            withoutRemember.persistSelectionIfNeeded(defaults: testDefaults)
            precondition(testDefaults.string(forKey: LaunchOptions.rememberedDataDirectoryKey) == nil, "Explicit data-dir without --remember-data-dir must not persist")
            let smokeRemember = LaunchOptions.parse(args: ["CampusPet", "--data-dir", explicitDir.path, "--remember-data-dir", "--smoke-test", tempRoot.path], defaults: testDefaults)
            smokeRemember.persistSelectionIfNeeded(defaults: testDefaults)
            precondition(testDefaults.string(forKey: LaunchOptions.rememberedDataDirectoryKey) == nil, "Smoke launch must never persist data-dir")
            let externalRemember = LaunchOptions.parse(args: ["CampusPet", "--data-dir", explicitDir.path, "--remember-data-dir", "--external-service"], defaults: testDefaults)
            externalRemember.persistSelectionIfNeeded(defaults: testDefaults)
            precondition(testDefaults.string(forKey: LaunchOptions.rememberedDataDirectoryKey) == nil, "External service launch must never persist data-dir")
            let rememberedOption = LaunchOptions.parse(args: ["CampusPet", "--data-dir", rememberedDir.path, "--project", "--remember-data-dir"], defaults: testDefaults)
            ServiceController(options: rememberedOption).persistSelectionIfNeeded(defaults: testDefaults)
            let restored = LaunchOptions.parse(args: ["CampusPet"], defaults: testDefaults)
            precondition(restored.dataDirectory == rememberedDir.standardizedFileURL && restored.projectMode, "Remembered existing path and project flag must be restored before default")
            let overrideExplicit = LaunchOptions.parse(args: ["CampusPet", "--data-dir", explicitDir.path], defaults: testDefaults)
            precondition(overrideExplicit.dataDirectory == explicitDir.standardizedFileURL && !overrideExplicit.projectMode, "Explicit --data-dir must take priority over remembered profile")
            try! FileManager.default.removeItem(at: rememberedDir)
            let fallbackAfterMissing = LaunchOptions.parse(args: ["CampusPet"], defaults: testDefaults)
            precondition(fallbackAfterMissing.dataDirectory != rememberedDir.standardizedFileURL, "Missing remembered path must fall back to default")
            var stopCalls = 0
            var replies: [Bool] = []
            app.terminationReplyHandler = { replies.append($0) }
            app.bypassServiceShutdownOnTerminate = true
            precondition(app.applicationShouldTerminate(NSApp) == .terminateNow, "Bypass flag must allow immediate termination")
            precondition(!app.bypassServiceShutdownOnTerminate && stopCalls == 0, "Bypass termination must reset flag and skip stopBackend")
            app.ready = true
            app.stopBackendOperation = { stopCalls += 1 }
            precondition(app.applicationShouldTerminate(NSApp) == .terminateLater, "Normal termination must wait for stopBackend")
            while replies.count < 1 { RunLoop.current.run(mode: .default, before: Date(timeIntervalSinceNow: 0.01)) }
            precondition(stopCalls == 1 && replies == [true] && !app.ready, "Successful stopBackend must reply true and clear ready")
            app.lastStopError = nil
            app.stopBackendOperation = {
                stopCalls += 1
                throw ServiceError.message("后台忙碌")
            }
            precondition(app.applicationShouldTerminate(NSApp) == .terminateLater, "Failed stopBackend must also use terminateLater")
            while replies.count < 2 { RunLoop.current.run(mode: .default, before: Date(timeIntervalSinceNow: 0.01)) }
            precondition(stopCalls == 2 && replies == [true, false] && app.lastStopError == "后台忙碌", "Failed stopBackend must reply false and report error")
            app.stopBackendOperation = nil
            app.terminationReplyHandler = nil
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
