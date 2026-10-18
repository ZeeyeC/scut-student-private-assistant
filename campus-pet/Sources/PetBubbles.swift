import AppKit

final class PetTaskBubbleButton: NSButton {
    var onComplete: (() -> Void)?
    var completing = false { didSet { isEnabled = !completing; needsDisplay = true } }
    private var hovering = false
    private var rightPressed = false
    private var hoverTracking: NSTrackingArea?

    func containsCircle(_ point: NSPoint) -> Bool {
        hypot(point.x - bounds.midX, point.y - bounds.midY) <= bounds.width / 2 - 2
    }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    override func hitTest(_ point: NSPoint) -> NSView? {
        containsCircle(convert(point, from: superview)) ? super.hitTest(point) : nil
    }
    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let hoverTracking { removeTrackingArea(hoverTracking) }
        let tracking = NSTrackingArea(rect: bounds, options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect], owner: self)
        addTrackingArea(tracking); hoverTracking = tracking
    }
    override func mouseEntered(with event: NSEvent) { hovering = true; needsDisplay = true }
    override func mouseExited(with event: NSEvent) { hovering = false; needsDisplay = true }
    override func rightMouseDown(with event: NSEvent) {
        rightPressed = isEnabled && containsCircle(convert(event.locationInWindow, from: nil))
    }
    override func rightMouseUp(with event: NSEvent) {
        defer { rightPressed = false }
        if rightPressed, isEnabled, containsCircle(convert(event.locationInWindow, from: nil)) { onComplete?() }
    }
    override func draw(_ dirtyRect: NSRect) {
        let shape = NSBezierPath(ovalIn: bounds.insetBy(dx: 2, dy: 2))
        let active = hovering || isHighlighted
        NSColor(srgbRed: active ? 0.88 : 1, green: active ? 0.95 : 0.99, blue: active ? 0.78 : 0.92, alpha: 0.99).setFill()
        shape.fill()
        NSColor(srgbRed: 0.57, green: 0.67, blue: 0.38, alpha: 0.85).setStroke()
        shape.lineWidth = active ? 2 : 1; shape.stroke()
        let text = completing ? "…" : title
        let attributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 16, weight: .semibold),
            .foregroundColor: NSColor(srgbRed: 0.27, green: 0.34, blue: 0.19, alpha: 1),
        ]
        let size = (text as NSString).size(withAttributes: attributes)
        (text as NSString).draw(at: NSPoint(x: bounds.midX - size.width / 2, y: bounds.midY - size.height / 2), withAttributes: attributes)
    }
}

final class PetTaskBubblePanel: PetPanel {
    let taskID: String
    let button: PetTaskBubbleButton

    init(task: PetScheduledTask, target: AnyObject, action: Selector) {
        taskID = task.id
        button = PetTaskBubbleButton(title: PetScheduledTask.abbreviation(task.title), target: target, action: action)
        let bounds = NSRect(x: 0, y: 0, width: PetTaskRingLayout.diameter, height: PetTaskRingLayout.diameter)
        super.init(contentRect: bounds, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        title = "今日待办：" + task.title
        isOpaque = false; backgroundColor = .clear; hasShadow = false
        hidesOnDeactivate = false; isReleasedWhenClosed = false
        level = NSWindow.Level(rawValue: NSWindow.Level.floating.rawValue + 1)
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        button.frame = bounds; button.isBordered = false
        button.setAccessibilityLabel(task.title)
        button.setAccessibilityHelp("左击查看任务详细；右击标记整个待办完成")
        contentView = button
    }
}

extension AppDelegate {
    func togglePetBubbles() {
        if taskRingOpen { hidePetBubbles(); return }
        guard panel.isVisible else { return }
        taskRingOpen = true
        ringFrames = PetTaskRingLayout.frames(near: panel.frame, within: panel.screen?.visibleFrame ?? NSScreen.main!.visibleFrame)
        ringSlots = []; todayTasks = []; pet.taskRingText = "正在读取今日安排…"
        pet.stopAction(); scheduleNextPerformance()
        bubbleLocalMonitor = NSEvent.addLocalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown, .keyDown]) { [weak self] event in
            let consumed = MainActor.assumeIsolated {
                guard let self else { return false }
                if event.type == .keyDown {
                    if event.keyCode == 53 { self.hidePetBubbles(); return true }
                } else if event.window !== self.panel && !self.taskBubbleWindows.values.contains(where: { $0 === event.window }) {
                    self.hidePetBubbles()
                }
                return false
            }
            return consumed ? nil : event
        }
        bubbleGlobalMonitor = NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown]) { [weak self] _ in
            MainActor.assumeIsolated { self?.hidePetBubbles() }
        }
        Task { await refreshTaskRing() }
    }

    func hidePetBubbles() {
        taskRingOpen = false; ringGeneration += 1; loadingTaskRing = false
        for window in taskBubbleWindows.values { window.close() }
        taskBubbleWindows = [:]; ringSlots = []; pet.taskRingText = nil
        if let bubbleLocalMonitor { NSEvent.removeMonitor(bubbleLocalMonitor) }
        if let bubbleGlobalMonitor { NSEvent.removeMonitor(bubbleGlobalMonitor) }
        bubbleLocalMonitor = nil; bubbleGlobalMonitor = nil
    }

    func refreshTaskRing() async {
        guard taskRingOpen, !loadingTaskRing else { return }
        guard ready, trusted(webView?.url) else { pet.taskRingText = "正在连接助手…"; return }
        loadingTaskRing = true; ringGeneration += 1
        let generation = ringGeneration
        defer { if generation == ringGeneration { loadingTaskRing = false } }
        do {
            guard let data = try await js("""
                const get = async path => {
                  const r = await fetch('/api/' + path, {cache:'no-store'});
                  if (!r.ok) throw new Error('今日待办读取失败'); return r.json();
                };
                const [tasks, blocks, settings] = await Promise.all(['tasks','plan-blocks','settings'].map(get));
                return {tasks, blocks, timezone: settings.data.timezone};
                """) as? [String: Any], let tasks = data["tasks"] as? [[String: Any]], let blocks = data["blocks"] as? [[String: Any]] else {
                throw ServiceError.message("今日待办数据格式有误")
            }
            guard taskRingOpen, generation == ringGeneration else { return }
            taskTimezone = data["timezone"] as? String ?? "Asia/Shanghai"
            todayTasks = PetScheduledTask.today(tasks: tasks, blocks: blocks, timezone: taskTimezone)
            renderTaskRing()
        } catch {
            guard taskRingOpen, generation == ringGeneration else { return }
            for window in taskBubbleWindows.values { window.close() }
            taskBubbleWindows = [:]; todayTasks = []; ringSlots = []
            pet.taskRingText = "读取失败，请重新展开"
        }
    }

    func renderTaskRing() {
        guard taskRingOpen else { return }
        ringSlots = PetTaskRingLayout.slots(ringSlots, tasks: todayTasks.map(\.id), capacity: ringFrames.count)
        let visible = Set(ringSlots.compactMap { $0 })
        for (id, window) in taskBubbleWindows where !visible.contains(id) { window.close() }
        taskBubbleWindows = taskBubbleWindows.filter { visible.contains($0.key) }
        for (index, id) in ringSlots.enumerated() {
            guard let id, let task = todayTasks.first(where: { $0.id == id }) else { continue }
            let window = taskBubbleWindows[id] ?? PetTaskBubblePanel(task: task, target: self, action: #selector(openTaskBubble(_:)))
            window.button.title = PetScheduledTask.abbreviation(task.title)
            window.button.completing = completingTasks.contains(id)
            window.button.toolTip = task.title + "\n左击查看详细 · 右击完成整个待办"
            window.button.setAccessibilityLabel(task.title)
            window.button.onComplete = { [weak self] in self?.completeTaskBubble(id) }
            window.setFrame(ringFrames[index], display: true)
            window.orderFrontRegardless(); taskBubbleWindows[id] = window
        }
        if todayTasks.isEmpty { pet.taskRingText = "今天没有待办安排" }
        else if visible.count < todayTasks.count { pet.taskRingText = "今日 \(todayTasks.count) 项 · 显示 \(visible.count) 项" }
        else { pet.taskRingText = "今日 \(todayTasks.count) 项 · 右击完成" }
    }

    @objc func openTaskBubble(_ sender: NSButton) {
        guard let window = sender.window as? PetTaskBubblePanel,
              !completingTasks.contains(window.taskID), let task = todayTasks.first(where: { $0.id == window.taskID }) else { return }
        showTaskDetails(task)
    }

    func completeTaskBubble(_ id: String) {
        guard let task = todayTasks.first(where: { $0.id == id }), !completingTasks.contains(id),
              ready, trusted(webView?.url) else { return }
        completingTasks.insert(id); taskBubbleWindows[id]?.button.completing = true
        ringGeneration += 1; loadingTaskRing = false
        Task {
            defer { completingTasks.remove(id); taskBubbleWindows[id]?.button.completing = false }
            do {
                _ = try await webView.callAsyncJavaScript("""
                    const token = (await (await fetch('/api/csrf')).json()).csrf_token;
                    const r = await fetch('/api/tasks/' + encodeURIComponent(id), {
                      method:'PATCH', headers:{'Content-Type':'application/json','X-CSRF-Token':token,'Idempotency-Key':key},
                      body:JSON.stringify({revision, status:'completed'})
                    });
                    if (!r.ok) {
                      const body = await r.json().catch(()=>({}));
                      throw new Error(typeof body.detail === 'string' ? body.detail : '任务完成未保存，请重试');
                    }
                    const saved = await r.json();
                    window.dispatchEvent(new Event('campus-task-updated'));
                    return saved;
                    """, arguments: ["id": id, "revision": task.revision, "key": UUID().uuidString], in: nil, contentWorld: .page)
                todayTasks.removeAll { $0.id == id }; renderTaskRing()
                await refreshTaskRing()
                await refreshReminders()
            } catch {
                await refreshTaskRing()
                if taskRingOpen {
                    pet.taskRingText = "完成失败，请右击重试"
                    taskBubbleWindows[id]?.button.toolTip = task.title + "\n" + error.localizedDescription
                }
            }
        }
    }
}
