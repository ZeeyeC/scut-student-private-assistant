import AppKit

extension AppDelegate {
    // Only reached through the existing isolated smoke guard and a separate flag.
    // This prepares test data and runs real handlers for a guided screen recording.
    func prepareRecordedDemo() {
        Task {
            guard let output = options.smokeDirectory else { return }
            do {
                try await waitFor("document.querySelector('.composer textarea')")
                _ = try await js("""
                    const token=(await (await fetch('/api/csrf')).json()).csrf_token;
                    const r=await fetch('/__test__/task-ring',{method:'POST',headers:{'X-CSRF-Token':token}});
                    if(!r.ok) throw new Error(await r.text()); return await r.json();
                    """)
                closePanel(); hidePetBubbles(); pet.mood = .idle
                let screen = NSScreen.screens[0].visibleFrame
                let size = NSSize(width: min(1024, screen.width - 40), height: min(680, screen.height - 40))
                let frame = NSRect(x: screen.midX - size.width / 2, y: screen.midY - size.height / 2, width: size.width, height: size.height)
                let stage = PetPanel(contentRect: frame, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
                stage.title = "Demo2.2 · 录屏演示"
                stage.backgroundColor = NSColor(srgbRed: 0.95, green: 0.97, blue: 0.92, alpha: 1)
                stage.isOpaque = true; stage.hasShadow = false; stage.hidesOnDeactivate = false
                stage.level = .normal
                stage.isReleasedWhenClosed = false
                let content = NSView(frame: NSRect(origin: .zero, size: size))
                @MainActor func label(_ text: String, _ rect: NSRect, _ font: NSFont) {
                    let field = NSTextField(labelWithString: text)
                    field.font = font; field.textColor = NSColor(srgbRed: 0.22, green: 0.33, blue: 0.20, alpha: 1)
                    field.frame = rect; content.addSubview(field)
                }
                label("Demo2.2  奶蛙助手", NSRect(x: 32, y: size.height - 58, width: size.width - 64, height: 36), .systemFont(ofSize: 26, weight: .semibold))
                label("今日已安排待办 · 圆形气泡 · 完成后自动补位", NSRect(x: 32, y: size.height - 90, width: size.width - 64, height: 24), .systemFont(ofSize: 15))
                label("① 点击奶蛙展开   ② 左击查看详情   ③ 右击完成任务", NSRect(x: 32, y: 42, width: size.width - 64, height: 24), .systemFont(ofSize: 16, weight: .medium))
                label("自动功能演示 / 真实 App 录屏 / 隔离资料 / 无声音", NSRect(x: 32, y: 16, width: size.width - 64, height: 20), .systemFont(ofSize: 12))
                stage.contentView = content; demoStage = stage
                stage.orderFrontRegardless()
                panel.setFrameOrigin(NSPoint(x: frame.minX + size.width * 0.31 - 95, y: frame.midY - 105))
                panel.orderFrontRegardless()
                assistant.level = NSWindow.Level(rawValue: NSWindow.Level.floating.rawValue + 2)
                assistant.setFrame(NSRect(x: frame.minX + 20, y: frame.minY + 20, width: size.width - 40, height: size.height - 120), display: false)
                // screencapture uses Quartz coordinates with the main display's top at 0.
                let quartzY = NSScreen.screens[0].frame.maxY - frame.maxY
                let info: [String: Any] = [
                    "pid": ProcessInfo.processInfo.processIdentifier,
                    "rect": [Int(frame.minX), Int(quartzY), Int(frame.width), Int(frame.height)],
                    "bundle_id": Bundle.main.bundleIdentifier ?? "",
                ]
                try JSONSerialization.data(withJSONObject: info, options: [.prettyPrinted, .sortedKeys])
                    .write(to: output.appendingPathComponent("recording-ready.json"))
                try await Task.sleep(nanoseconds: 5_000_000_000)
                togglePetBubbles()
                try await waitForNative("录屏任务环") { !loadingTaskRing && taskBubbleWindows.count == 6 }
                try await Task.sleep(nanoseconds: 5_000_000_000)
                taskBubbleWindows["ring-task-0"]?.button.performClick(nil)
                try await waitForNative("录屏任务详情") { taskDetails?.textView.string.contains("任务要求验收") == true }
                try await Task.sleep(nanoseconds: 7_000_000_000)
                taskDetails?.orderOut(nil); togglePetBubbles()
                try await waitForNative("录屏重新展开") { !loadingTaskRing && taskBubbleWindows.count == 6 }
                try await Task.sleep(nanoseconds: 3_000_000_000)
                completeTaskBubble("ring-task-0")
                try await waitForNative("录屏自动补位") { !loadingTaskRing && taskBubbleWindows["ring-task-6"] != nil }
                try await Task.sleep(nanoseconds: 5_000_000_000)
                completeTaskBubble("ring-task-1")
                try await waitForNative("录屏第二次补位") { !loadingTaskRing && taskBubbleWindows["ring-task-7"] != nil }
                try await Task.sleep(nanoseconds: 5_000_000_000)
                for id in ["ring-task-2", "ring-task-3", "ring-task-4", "ring-task-5", "ring-task-6", "ring-task-7"] {
                    completeTaskBubble(id)
                    try await waitForNative("录屏保存完成") { !completingTasks.contains(id) && !loadingTaskRing && taskBubbleWindows[id] == nil }
                    try await Task.sleep(nanoseconds: 1_000_000_000)
                }
                guard todayTasks.isEmpty else { throw ServiceError.message("录屏任务未完成") }
                try "完成真实任务读取、详情、写入、补位与空状态。".write(to: output.appendingPathComponent("demo-flow-passed.txt"), atomically: true, encoding: .utf8)
            } catch {
                try? error.localizedDescription.write(to: output.appendingPathComponent("recording-error.txt"), atomically: true, encoding: .utf8)
                NSApp.terminate(nil)
            }
        }
    }
}
