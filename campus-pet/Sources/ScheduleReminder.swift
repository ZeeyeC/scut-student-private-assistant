import AppKit

struct ScheduleReminder {
    let key: String
    let title: String
    let startsAt: Date
    let targetKind: String
    let target: String
    let announced: Bool

    init?(_ data: [String: Any]) {
        guard let key = data["key"] as? String, let title = data["title"] as? String,
              let start = data["starts_at"] as? String,
              let date = Self.parseDate(start) else { return nil }
        self.key = key; self.title = title; self.startsAt = date
        self.targetKind = data["target_kind"] as? String ?? "none"
        self.target = data["target"] as? String ?? ""
        self.announced = data["announced"] as? Bool ?? false
    }

    static func parseDate(_ value: String) -> Date? {
        let formatter = ISO8601DateFormatter()
        if let date = formatter.date(from: value) { return date }
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.date(from: value)
    }

    var destination: URL? {
        if targetKind == "website", let url = URL(string: target),
           ["http", "https"].contains(url.scheme?.lowercased() ?? ""), url.host != nil,
           url.user == nil, url.password == nil { return url }
        if targetKind == "file", target.hasPrefix("/"), !target.contains("\0") {
            return URL(fileURLWithPath: target)
        }
        return nil
    }
}

extension AppDelegate {
    func refreshReminders() async {
        guard ready, trusted(webView?.url), !checkingReminders else { return }
        checkingReminders = true
        defer { checkingReminders = false }
        do {
            guard let values = try await js("const r = await fetch('/api/schedule-reminders', {cache:'no-store'}); if(!r.ok) throw new Error('Reminders unavailable'); return await r.json();") as? [[String: Any]] else { return }
            let existing = Set(pendingReminders.map(\.key))
            pendingReminders = values.compactMap(ScheduleReminder.init).filter {
                $0.startsAt > Date() && !dismissedReminders.contains($0.key) && (!$0.announced || existing.contains($0.key))
            }
            await presentScheduleReminder()
        } catch {
            // Keep the last reminder during a transient disconnect, but never open
            // a cached destination without revalidating it on click.
            pendingReminders.removeAll { $0.startsAt <= Date() }
            pet.reminderText = pendingReminders.first.map { "快开始：" + String($0.title.prefix(9)) }
            pet.needsDisplay = true
        }
    }

    func presentScheduleReminder() async {
        pet.reminderText = pendingReminders.first.map { "快开始：" + String($0.title.prefix(9)) }
        pet.needsDisplay = true
        guard let first = pendingReminders.first else { return }
        if announcedReminders.insert(first.key).inserted {
            pet.stopAction(); panel.orderFrontRegardless()

        }
        guard !first.announced else { return }
        let literal = String(data: try! JSONSerialization.data(withJSONObject: [first.key]), encoding: .utf8)!
        _ = try? await js("const token = (await (await fetch('/api/csrf')).json()).csrf_token; const r = await fetch('/api/schedule-reminders/ack', {method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':token},body:JSON.stringify({key:\(literal)[0]})}); return r.ok;")
    }

    func openScheduleReminder() {
        hidePetBubbles()
        guard !openingReminder, let original = pendingReminders.first else { return }
        openingReminder = true
        Task {
            defer { openingReminder = false }
            do {
                guard let values = try await js("const r=await fetch('/api/schedule-reminders',{cache:'no-store'}); if(!r.ok) throw new Error('Offline'); return await r.json();") as? [[String: Any]] else { return }
                guard let reminder = values.compactMap(ScheduleReminder.init).first(where: { $0.key == original.key && $0.startsAt > Date() }) else {
                    dismissedReminders.insert(original.key); pendingReminders.removeAll { $0.key == original.key }
                    await presentScheduleReminder(); showAssistant(page: "作业"); return
                }
                if reminder.targetKind == "none" { showAssistant(page: "作业") }
                else {
                    guard let url = reminder.destination else { throw ServiceError.message("快捷方式地址无效，请在日程详情中重新设置。") }
                    if url.isFileURL && !FileManager.default.fileExists(atPath: url.path) {
                        throw ServiceError.message("文件已移动或删除，请在日程详情中重新选择文件。")
                    }
                    guard NSWorkspace.shared.open(url) else { throw ServiceError.message("无法打开该内容，请检查默认应用和文件权限。") }
                }
                dismissedReminders.insert(reminder.key); pendingReminders.removeAll { $0.key == reminder.key }
                await presentScheduleReminder()
            } catch {
                let alert = NSAlert(); alert.messageText = "暂时无法打开日程快捷方式"
                alert.informativeText = "请确认本机助手连接正常。\n" + error.localizedDescription
                alert.runModal()
            }
        }
    }

    func chooseReminderFile() {
        let picker = NSOpenPanel()
        picker.canChooseDirectories = false; picker.canChooseFiles = true
        picker.allowsMultipleSelection = false; picker.prompt = "用于日程快捷打开"
        picker.beginSheetModal(for: assistant) { [weak self] result in
            guard result == .OK, let path = picker.url?.path, let self else { return }
            let literal = String(data: try! JSONSerialization.data(withJSONObject: [path]), encoding: .utf8)!
            self.webView.evaluateJavaScript("window.dispatchEvent(new CustomEvent('campus-reminder-file',{detail:\(literal)[0]}));")
        }
    }
}
