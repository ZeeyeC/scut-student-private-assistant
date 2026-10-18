import AppKit
import WebKit

final class TaskDetailsWindow: NSWindow {
    let textView = NSTextView()
    var request = UUID()

    init(target: AppDelegate) {
        super.init(contentRect: NSRect(x: 0, y: 0, width: 440, height: 530), styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
        title = "待办详情"; minSize = NSSize(width: 360, height: 360)
        isReleasedWhenClosed = false; delegate = target
        let content = NSView(); contentView = content
        let scroll = NSScrollView(); scroll.hasVerticalScroller = true
        scroll.translatesAutoresizingMaskIntoConstraints = false
        textView.isEditable = false; textView.isSelectable = true
        textView.isRichText = false; textView.textContainerInset = NSSize(width: 20, height: 20)
        textView.isVerticallyResizable = true; textView.isHorizontallyResizable = false
        textView.autoresizingMask = [.width]
        textView.textContainer?.widthTracksTextView = true
        textView.backgroundColor = NSColor(srgbRed: 1, green: 0.99, blue: 0.95, alpha: 1)
        textView.setAccessibilityLabel("待办详细内容")
        scroll.documentView = textView; content.addSubview(scroll)
        let all = NSButton(title: "打开待办与日程", target: target, action: #selector(AppDelegate.openTodos))
        let close = NSButton(title: "关闭", target: self, action: #selector(NSWindow.performClose(_:)))
        let footer = NSStackView(views: [all, close]); footer.spacing = 12
        footer.translatesAutoresizingMaskIntoConstraints = false; content.addSubview(footer)
        NSLayoutConstraint.activate([
            scroll.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            scroll.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            scroll.topAnchor.constraint(equalTo: content.topAnchor),
            scroll.bottomAnchor.constraint(equalTo: footer.topAnchor, constant: -12),
            footer.centerXAnchor.constraint(equalTo: content.centerXAnchor),
            footer.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -12),
        ])
    }

    func display(_ text: String) {
        let style = NSMutableParagraphStyle(); style.lineSpacing = 5
        textView.textStorage?.setAttributedString(NSAttributedString(string: text, attributes: [
            .font: NSFont.systemFont(ofSize: 14), .foregroundColor: NSColor.labelColor, .paragraphStyle: style,
        ]))
        textView.scrollToBeginningOfDocument(nil)
    }
}

extension AppDelegate {
    @objc func openTodos() { taskDetails?.orderOut(nil); showAssistant(page: "作业") }

    func showTaskDetails(_ selected: PetScheduledTask) {
        hidePetBubbles()
        if taskDetails == nil {
            taskDetails = TaskDetailsWindow(target: self)
            taskDetails?.center()
        }
        guard let window = taskDetails else { return }
        if let demoStage {
            window.level = NSWindow.Level(rawValue: NSWindow.Level.floating.rawValue + 2)
            window.setFrameOrigin(NSPoint(x: demoStage.frame.maxX - window.frame.width - 20, y: demoStage.frame.midY - window.frame.height / 2))
        }
        window.request = UUID(); let request = window.request
        window.display(selected.title + "\n\n正在读取待办详情…")
        NSApp.activate(ignoringOtherApps: true); window.makeKeyAndOrderFront(nil)
        Task {
            do {
                guard ready, trusted(webView?.url) else { throw ServiceError.message("请先连接本机助手") }
                let response = try await webView.callAsyncJavaScript("""
                    const get = async path => {
                      const r = await fetch('/api/' + path, {cache:'no-store'});
                      if (!r.ok) throw new Error(r.status === 404 ? '待办已删除，请重新展开任务' : '待办详情暂时无法读取');
                      return r.json();
                    };
                    const [task, steps, blocks, settings] = await Promise.all([
                      'tasks/' + encodeURIComponent(id), 'tasks/' + encodeURIComponent(id) + '/steps', 'plan-blocks', 'settings'
                    ].map(get));
                    return {task, steps, blocks, timezone:settings.data.timezone};
                    """, arguments: ["id": selected.id], in: nil, contentWorld: .page)
                guard let response = response as? [String: Any], let task = response["task"] as? [String: Any],
                      let data = task["data"] as? [String: Any] else { throw ServiceError.message("待办详情数据格式有误") }
                guard request == window.request else { return }
                let tz = response["timezone"] as? String ?? "Asia/Shanghai"
                let scheduled = PetScheduledTask.today(tasks: [task], blocks: response["blocks"] as? [[String: Any]] ?? [], timezone: tz).first
                let formatter = DateFormatter(); formatter.locale = Locale(identifier: "zh_CN")
                formatter.timeZone = TimeZone(identifier: tz); formatter.dateFormat = "MM月dd日 HH:mm"
                func date(_ value: Any?) -> String {
                    guard let value = value as? String, let instant = ScheduleReminder.parseDate(value) else { return "待确认" }
                    return formatter.string(from: instant)
                }
                var lines = [data["title"] as? String ?? selected.title, "", "状态：" + (["open":"进行中", "completed":"已完成", "archived":"已归档"][data["status"] as? String ?? ""] ?? "未知"), "截止：" + date(data["due_at"])]
                if let method = data["submission_method"] as? String, !method.isEmpty { lines.append("提交方式：" + method) }
                lines += ["", "今天的安排（\(tz)）"]
                for block in scheduled?.blocks ?? [] { lines.append(date(block["starts_at"]) + " — " + date(block["ends_at"])) }
                if scheduled == nil { lines.append("目前没有未完成的当日安排。") }
                lines += ["", "任务要求"]
                let requirements = data["requirements"] as? [String] ?? []
                lines += requirements.isEmpty ? ["未填写具体要求。"] : requirements.map { "• " + $0 }
                let steps = response["steps"] as? [[String: Any]] ?? []
                if !steps.isEmpty { lines += ["", "步骤"] }
                for row in steps {
                    guard let step = row["data"] as? [String: Any] else { continue }
                    lines.append((step["status"] as? String == "completed" ? "✓ " : "○ ") + (step["title"] as? String ?? "学习步骤"))
                    if let description = step["description"] as? String, !description.isEmpty { lines.append(description) }
                }
                window.display(lines.joined(separator: "\n"))
            } catch {
                if request == window.request { window.display(selected.title + "\n\n读取失败：" + error.localizedDescription + "\n\n关闭后可重新点击任务气泡。") }
            }
        }
    }
}
