import AppKit
import WebKit
import UniformTypeIdentifiers

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler, NSWindowDelegate {
    let options = LaunchOptions.parse()
    lazy var service = ServiceController(options: options)
    let pet = PetView(frame: NSRect(x: 0, y: 0, width: 190, height: 210))
    var panel: PetPanel!
    var taskRingOpen = false
    var taskBubbleWindows: [String: PetTaskBubblePanel] = [:]
    var ringFrames: [NSRect] = []
    var ringSlots: [String?] = []
    var todayTasks: [PetScheduledTask] = []
    var taskTimezone = "Asia/Shanghai"
    var ringGeneration = 0
    var loadingTaskRing = false
    var completingTasks = Set<String>()
    var taskDetails: TaskDetailsWindow?
    var demoStage: NSWindow?
    var bubbleLocalMonitor: Any?
    var bubbleGlobalMonitor: Any?
    var browserOpener: (URL) -> Bool = { NSWorkspace.shared.open($0) }
    var assistant: NSWindow!
    var webView: WKWebView!
    var statusItem: NSStatusItem!
    var timer: Timer?
    var reminderTimer: Timer?
    var pendingReminders: [ScheduleReminder] = []
    var announcedReminders = Set<String>()
    var dismissedReminders = Set<String>()
    var checkingReminders = false
    var openingReminder = false
    var sleeping = false
    var latestAssistantMood: PetMood = .starting
    var ready = false
    var starting = false
    var compact = true
    var dragInProgress = false
    var requestedPage = "助手"
    var segments: NSSegmentedControl!
    var smokeStarted = false
    var automaticActions = true
    var stoppingService = false
    var exitConfirmation: NSAlert?
    var nextPerformanceAt = ProcessInfo.processInfo.systemUptime + 20

    func applicationDidFinishLaunching(_ notification: Notification) {
        if options.smokeDirectory != nil {
            guard !options.projectMode, options.externalService, assistantOrigin.port != 5173,
                  FileManager.default.fileExists(atPath: options.dataDirectory.appendingPathComponent(".pet-smoke-isolated").path) else {
                finishSmoke(error: "验收仅允许独立端口、带隔离标记的临时目录和测试服务。")
                return
            }
        }
        // One pet per app bundle, while allowing isolated smoke-test instances.
        if options.smokeDirectory == nil,
           let identifier = Bundle.main.bundleIdentifier,
           let existing = NSRunningApplication.runningApplications(withBundleIdentifier: identifier)
            .first(where: { $0.processIdentifier != ProcessInfo.processInfo.processIdentifier }) {
            existing.activate(options: [.activateAllWindows])
            NSApp.terminate(nil); return
        }
        NSApp.setActivationPolicy(.accessory)
        if options.smokeDirectory == nil {
            automaticActions = UserDefaults.standard.object(forKey: "automaticActions") as? Bool ?? true
        } else { automaticActions = false }
        installMenus()
        makePet()
        makeAssistant()
        NotificationCenter.default.addObserver(self, selector: #selector(screenChanged), name: NSApplication.didChangeScreenParametersNotification, object: nil)
        timer = Timer.scheduledTimer(withTimeInterval: 1.0 / 20.0, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.animate() }
        }
        reminderTimer = Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { [weak self] _ in
            Task { @MainActor in
                await self?.refreshReminders()
                await self?.refreshTaskRing()
            }
        }
        beginService()
    }

    func makePet() {
        panel = PetPanel(contentRect: pet.bounds, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        panel.title = "课间桌宠"
        panel.isOpaque = false; panel.backgroundColor = .clear
        panel.hasShadow = false; panel.hidesOnDeactivate = false
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.isReleasedWhenClosed = false
        panel.contentView = pet
        pet.setAccessibilityElement(true)
        pet.setAccessibilityRole(.button)
        pet.setAccessibilityLabel("奶蛙，点击环形展开今天已安排的待办，左击任务查看详细，右击任务完成，拖动移动，紫色时点击肚皮打开任务")
        pet.onClick = { [weak self] in
            guard let self else { return }
            self.scheduleNextPerformance()
            if self.sleeping { self.toggleSleep() }
            self.togglePetBubbles()
        }
        pet.onReminderClick = { [weak self] in self?.openScheduleReminder() }
        pet.onMenu = { [weak self] event in
            guard let self else { return }
            self.hidePetBubbles()
            NSMenu.popUpContextMenu(self.petMenu(), with: event, for: self.pet)
        }
        pet.onDragStart = { [weak self] in self?.hidePetBubbles() }
        pet.onMove = { [weak self] in self?.constrainAndSave(); self?.scheduleNextPerformance() }
        if options.smokeDirectory == nil, let stored = UserDefaults.standard.string(forKey: "petOrigin") {
            panel.setFrameOrigin(NSPointFromString(stored))
        } else {
            let visible = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1200, height: 800)
            panel.setFrameOrigin(NSPoint(x: visible.maxX - 215, y: visible.minY + 40))
        }
        constrainAndSave()
        panel.orderFrontRegardless()
    }

    func makeAssistant() {
        let content = NSView(frame: NSRect(x: 0, y: 0, width: 560, height: 720))
        assistant = NSWindow(contentRect: content.bounds, styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        assistant.title = "课间 · 桌宠助手"
        assistant.minSize = NSSize(width: 440, height: 500)
        assistant.isReleasedWhenClosed = false
        assistant.delegate = self
        assistant.contentView = content
        assistant.center()
        assistant.setFrameAutosaveName("CampusPetAssistant")
        let config = WKWebViewConfiguration()
        config.websiteDataStore = options.smokeDirectory == nil ? .default() : .nonPersistent()
        let scripts = config.userContentController
        scripts.add(self, name: "petState")
        if let scriptURL = Bundle.main.url(forResource: "Bridge", withExtension: "js"),
           let js = try? String(contentsOf: scriptURL, encoding: .utf8) {
            scripts.addUserScript(WKUserScript(source: js, injectionTime: .atDocumentEnd, forMainFrameOnly: true))
        }
        webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = self; webView.uiDelegate = self
        webView.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(webView)
        let bar = NSStackView()
        bar.orientation = .horizontal; bar.spacing = 8
        bar.translatesAutoresizingMaskIntoConstraints = false
        segments = NSSegmentedControl(labels: ["助手", "今日", "课表", "待办与日程", "设置"], trackingMode: .selectOne, target: self, action: #selector(changePage))
        segments.selectedSegment = 0
        bar.addArrangedSubview(segments)
        let expand = NSButton(title: "展开", target: self, action: #selector(toggleLayout))
        expand.toolTip = "切换紧凑面板 / 完整工作台"
        bar.addArrangedSubview(expand)
        content.addSubview(bar)
        let browser = NSButton(title: "课表导入请在浏览器打开", target: self, action: #selector(openBrowser))
        browser.bezelStyle = .inline; browser.font = .systemFont(ofSize: 11)
        let review = NSButton(title: "查看待校对", target: self, action: #selector(showReview))
        review.bezelStyle = .inline; review.font = .systemFont(ofSize: 11)
        let links = NSStackView(views: [browser, review])
        links.spacing = 14; links.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(links)
        NSLayoutConstraint.activate([
            bar.topAnchor.constraint(equalTo: content.topAnchor, constant: 10),
            bar.centerXAnchor.constraint(equalTo: content.centerXAnchor),
            links.topAnchor.constraint(equalTo: bar.bottomAnchor, constant: 7),
            links.centerXAnchor.constraint(equalTo: content.centerXAnchor),
            webView.topAnchor.constraint(equalTo: links.bottomAnchor, constant: 8),
            webView.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            webView.bottomAnchor.constraint(equalTo: content.bottomAnchor),
        ])
    }

    func installMenus() {
        let mainMenu = NSMenu()
        let appItem = NSMenuItem(); mainMenu.addItem(appItem)
        let menu = NSMenu()
        menu.addItem(item("打开助手", #selector(openChat), "1"))
        menu.addItem(item("显示桌宠", #selector(showPet), "0"))
        menu.addItem(.separator())
        menu.addItem(item("关闭助手面板", #selector(closePanel), "w"))
        menu.addItem(item("仅退出桌宠（后台继续运行）", #selector(quit), "q"))
        appItem.submenu = menu
        let editItem = NSMenuItem(title: "编辑", action: nil, keyEquivalent: "")
        let edit = NSMenu(title: "编辑")
        for (title, selector, key) in [("撤销", "undo:", "z"), ("剪切", "cut:", "x"), ("复制", "copy:", "c"), ("粘贴", "paste:", "v"), ("全选", "selectAll:", "a")] {
            edit.addItem(NSMenuItem(title: title, action: Selector(selector), keyEquivalent: key))
        }
        editItem.submenu = edit; mainMenu.addItem(editItem)
        NSApp.mainMenu = mainMenu
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.image = NSImage(systemSymbolName: "sparkles", accessibilityDescription: "课间桌宠")
        statusItem.button?.toolTip = "课间 · 桌宠助手"
        statusItem.menu = petMenu()
    }

    func item(_ title: String, _ action: Selector, _ key: String = "") -> NSMenuItem {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: key)
        item.target = self
        return item
    }

    func petMenu() -> NSMenu {
        let menu = NSMenu(title: "课间")
        menu.addItem(item("和我聊聊", #selector(openChat)))
        menu.addItem(item("今日安排", #selector(openToday)))
        menu.addItem(item("课后作业询问", #selector(openHomework)))
        menu.addItem(item("模型与设置", #selector(openSettings)))
        menu.addItem(item("显示桌宠", #selector(showPet)))
        menu.addItem(item("隐藏桌宠（菜单栏可恢复）", #selector(hidePet)))
        menu.addItem(item("暂停 / 恢复动画", #selector(toggleSleep)))
        let actionItem = NSMenuItem(title: "表演动作", action: nil, keyEquivalent: "")
        let actions = NSMenu(title: "表演动作")
        for action in PetAction.allCases {
            let entry = item(action.title, #selector(performAction(_:)))
            entry.representedObject = action.rawValue
            actions.addItem(entry)
        }
        actions.addItem(.separator())
        actions.addItem(item("停止当前动作", #selector(stopPerformance)))
        actionItem.submenu = actions; menu.addItem(actionItem)
        let automatic = item("自由表演（空闲时随机动作）", #selector(toggleAutomaticActions))
        automatic.state = automaticActions ? .on : .off
        menu.addItem(automatic)
        menu.addItem(.separator())
        menu.addItem(item("在浏览器中打开完整助手", #selector(openBrowser)))
        menu.addItem(item("重新连接本机服务", #selector(reconnect)))
        let exit = NSMenuItem(title: "关闭与退出", action: nil, keyEquivalent: "")
        let exits = NSMenu(title: "关闭与退出")
        exits.addItem(item("仅退出桌宠（后台继续运行）", #selector(quit)))
        exits.addItem(item("停止后台并退出…", #selector(stopServiceAndQuit)))
        exit.submenu = exits; menu.addItem(exit)
        return menu
    }

    func beginService() {
        guard !starting else { return }
        starting = true; ready = false; receiveAssistantMood(.starting)
        let startingHTML = "<html lang='zh'><meta charset='utf-8'><body style='font:15px -apple-system;padding:36px;background:#f5f8f3;color:#24453c'><h2>课间，陪你一起完成。</h2><p>正在连接本机助手…</p><p>点击奶蛙环形展开今日已安排的待办，左击任务查看详细，右击任务完成。</p></body></html>"
        webView.loadHTMLString(startingHTML, baseURL: nil)
        Task {
            do {
                try await service.start()
                ready = true; starting = false; receiveAssistantMood(.idle)
                webView.load(URLRequest(url: assistantOrigin))
            } catch {
                starting = false; receiveAssistantMood(.error)
                let safe = error.localizedDescription.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;")
                webView.loadHTMLString("<meta charset='utf-8'><body style='font:15px -apple-system;padding:32px'><h2>暂时没有连接成功</h2><p>\(safe)</p><p>处理后，点击菜单栏「重新连接本机服务」。</p></body>", baseURL: nil)
                showAssistant()
                if options.smokeDirectory != nil { finishSmoke(error: error.localizedDescription) }
            }
        }
    }

    func showAssistant(page: String? = nil) {
        hidePetBubbles()
        if let page { requestedPage = page }
        NSApp.activate(ignoringOtherApps: true)
        assistant.makeKeyAndOrderFront(nil)
        navigate()
        checkAfterClass()
    }

    func navigate() {
        let pages = ["助手", "今日", "课表", "作业", "设置"]
        guard let index = pages.firstIndex(of: requestedPage) else { return }
        segments.selectedSegment = index
        let literal = String(data: try! JSONSerialization.data(withJSONObject: [requestedPage]), encoding: .utf8)!
        webView.evaluateJavaScript("window.__campusPet?.navigate(\(literal)[0]);") { _, _ in }
    }

    func animate() {
        guard let panel, panel.isVisible else { return }
        pet.reducedMotion = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
        if pet.reducedMotion, pet.activeAction != nil { pet.stopAction() }
        if !sleeping && !pet.reducedMotion {
            pet.advanceAnimation(by: 0.05)
            if automaticActions, !taskRingOpen, pet.reminderText == nil, pet.mood == .idle, pet.activeAction == nil,
               NSEvent.pressedMouseButtons == 0,
               ProcessInfo.processInfo.systemUptime >= nextPerformanceAt {
                if let action = PetAction.allCases.randomElement() { pet.play(action) }
                scheduleNextPerformance()
            }
        }
        // A transparent rectangle must not steal clicks from apps below it.
        // Keep mouse events enabled while dragging, even beyond our old frame.
        let point = panel.convertPoint(fromScreen: NSEvent.mouseLocation)
        if NSEvent.pressedMouseButtons == 0 {
            panel.ignoresMouseEvents = !pet.isInteractive(point)
            for window in taskBubbleWindows.values {
                let local = window.convertPoint(fromScreen: NSEvent.mouseLocation)
                window.ignoresMouseEvents = !window.button.containsCircle(local)
            }
        }
    }

    func constrainAndSave() {
        let frames = NSScreen.screens.map(\.visibleFrame)
        let frame = panel.frame
        let best = frames.max { a, b in
            let ia = a.intersection(frame), ib = b.intersection(frame)
            return ia.width * ia.height < ib.width * ib.height
        } ?? NSRect(x: 0, y: 0, width: 1200, height: 800)
        panel.setFrameOrigin(NSPoint(x: min(max(frame.minX, best.minX), best.maxX - frame.width), y: min(max(frame.minY, best.minY), best.maxY - frame.height)))
        if options.smokeDirectory == nil {
            UserDefaults.standard.set(NSStringFromPoint(panel.frame.origin), forKey: "petOrigin")
        }
    }

    @objc func screenChanged() { hidePetBubbles(); constrainAndSave() }
    @objc func openChat() { showAssistant(page: "助手") }
    @objc func openToday() { showAssistant(page: "今日") }
    @objc func openHomework() { showAssistant(page: "今日"); checkAfterClass(manual: true) }
    func checkAfterClass(manual: Bool = false) {
        guard ready else { return }
        webView.evaluateJavaScript("window.dispatchEvent(new CustomEvent('campus-after-class-open', {detail:{manual:\(manual ? "true" : "false")}}));") { _, _ in }
    }
    func applicationDidBecomeActive(_ notification: Notification) { checkAfterClass() }
    @objc func openSettings() { showAssistant(page: "设置") }
    @objc func showReview() {
        showAssistant(page: "助手")
        webView.evaluateJavaScript("window.__campusPet?.showReview();")
    }
    @objc func showPet() { panel.orderFrontRegardless(); constrainAndSave(); scheduleNextPerformance() }
    @objc func hidePet() { hidePetBubbles(); panel.orderOut(nil) }
    @objc func closePanel() { assistant.orderOut(nil) }
    @objc func quit() { NSApp.terminate(nil) }
    @objc func stopServiceAndQuit() {
        guard !stoppingService, exitConfirmation == nil else { return }
        guard ready, trusted(webView?.url) else {
            showStopError(starting ? "正在启动后台，请稍后重试；也可以选择仅退出桌宠。" : "尚未连接本机助手。请先重新连接，或选择仅退出桌宠。")
            return
        }
        let alert = NSAlert()
        alert.messageText = "停止后台并退出桌宠？"
        alert.informativeText = "浏览器中的 Web UI 也会断开。请先保存正在编辑或校对的内容。个人资料和模型配置会保留。"
        alert.addButton(withTitle: "停止后台并退出")
        alert.addButton(withTitle: "取消")
        // Cancelling, including Escape or closing the sheet, is side-effect free.
        alert.buttons.last?.keyEquivalent = "\u{1b}"
        exitConfirmation = alert
        NSApp.activate(ignoringOtherApps: true)
        assistant.makeKeyAndOrderFront(nil)
        alert.beginSheetModal(for: assistant) { [weak self] response in
            guard let self else { return }
            self.exitConfirmation = nil
            guard response == .alertFirstButtonReturn else { return }
            Task {
                do { try await self.stopBackend(); self.quit() }
                catch { self.showStopError(error.localizedDescription) }
            }
        }
    }
    func stopBackend() async throws {
        guard !stoppingService else { throw ServiceError.message("正在停止后台，请稍候。") }
        guard ready, trusted(webView?.url) else { throw ServiceError.message("尚未连接本机助手，请先重新连接。") }
        stoppingService = true
        defer { stoppingService = false }
        let result: Any?
        do {
            result = try await webView.callAsyncJavaScript(ServiceController.shutdownJavaScript, arguments: [:], in: nil, contentWorld: .page)
        } catch {
            throw ServiceError.message("停止请求未能完成。请检查助手连接后重试；桌宠已保留，也可选择仅退出桌宠。")
        }
        guard let reply = result as? [String: Any], reply["stopping"] as? Bool == true else {
            throw ServiceError.message((result as? [String: Any])?["reason"] as? String ?? "后台没有接受停止请求，请稍后重试。")
        }
        try await service.waitUntilStopped()
        ready = false
    }
    func showStopError(_ message: String) {
        let alert = NSAlert()
        alert.messageText = "未能停止后台"
        alert.informativeText = message
        alert.addButton(withTitle: "知道了")
        NSApp.activate(ignoringOtherApps: true)
        assistant.makeKeyAndOrderFront(nil)
        alert.beginSheetModal(for: assistant) { _ in }
    }
    @objc func reconnect() { beginService() }
    @objc func toggleSleep() {
        if !sleeping { latestAssistantMood = pet.mood }
        sleeping.toggle(); pet.mood = sleeping ? .sleeping : latestAssistantMood
        scheduleNextPerformance()
    }
    func receiveAssistantMood(_ mood: PetMood) {
        latestAssistantMood = mood
        if mood != .idle { pet.stopAction(); scheduleNextPerformance() }
        if !sleeping { pet.mood = mood }
    }
    func scheduleNextPerformance() {
        nextPerformanceAt = ProcessInfo.processInfo.systemUptime + Double.random(in: 18...32)
    }
    @objc func performAction(_ sender: NSMenuItem) {
        guard let key = sender.representedObject as? String, let action = PetAction(rawValue: key) else { return }
        pet.reducedMotion = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
        if sleeping { toggleSleep() }
        pet.play(action)
        scheduleNextPerformance()
        panel.orderFrontRegardless()
    }
    @objc func stopPerformance() { pet.stopAction(); scheduleNextPerformance() }
    @objc func toggleAutomaticActions() {
        automaticActions.toggle()
        if options.smokeDirectory == nil { UserDefaults.standard.set(automaticActions, forKey: "automaticActions") }
        scheduleNextPerformance()
        statusItem.menu = petMenu()
    }
    @objc func changePage() {
        requestedPage = ["助手", "今日", "课表", "作业", "设置"][segments.selectedSegment]
        navigate()
    }
    @objc func toggleLayout(_ sender: NSButton) {
        compact.toggle()
        sender.title = compact ? "展开" : "收起"
        webView.evaluateJavaScript("window.__campusPet?.layout(\(compact));")
        var frame = assistant.frame
        frame.size.width = compact ? 560 : 1120
        frame.size.height = compact ? 720 : 820
        let visible = assistant.screen?.visibleFrame ?? NSScreen.main!.visibleFrame
        frame.size.width = min(frame.width, visible.width)
        frame.size.height = min(frame.height, visible.height)
        frame.origin.x = min(max(visible.minX, frame.minX), visible.maxX - frame.width)
        frame.origin.y = min(max(visible.minY, frame.minY), visible.maxY - frame.height)
        assistant.setFrame(frame, display: true, animate: true)
    }
    @objc func openBrowser() {
        hidePetBubbles()
        // WebKit does not run the existing Chrome/Edge timetable extension.
        _ = browserOpener(assistantOrigin)
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showPet(); showAssistant(); return true
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationWillTerminate(_ notification: Notification) {
        timer?.invalidate()
        reminderTimer?.invalidate()
        hidePetBubbles()
        // The service may be shared with the original app/browser. Do not kill it.
    }
    func windowShouldClose(_ sender: NSWindow) -> Bool { sender.orderOut(nil); return false }

    func trusted(_ url: URL?) -> Bool {
        guard let url else { return false }
        return url.scheme == "http" && url.host == "127.0.0.1" && url.port == assistantOrigin.port
    }
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        if trusted(url) || url.absoluteString == "about:blank" { decisionHandler(.allow); return }
        if navigationAction.navigationType == .linkActivated && ["https", "http"].contains(url.scheme ?? "") { NSWorkspace.shared.open(url) }
        decisionHandler(.cancel)
    }
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url, ["http", "https"].contains(url.scheme ?? "") { NSWorkspace.shared.open(url) }
        return nil
    }
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.frameInfo.isMainFrame, trusted(message.frameInfo.request.url),
              let value = message.body as? String else { return }
        if value == "choose-reminder-file" { chooseReminderFile(); return }
        if value == "after-class-due" {
            pet.stopAction(); showAssistant(); return
        }
        if value == "calendar-saved" {
            requestedPage = "作业"; segments.selectedSegment = 3; return
        }
        guard let mood = PetMood(rawValue: value) else { return }
        receiveAssistantMood(mood)
    }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        guard trusted(webView.url) else { return }
        navigate()
        webView.evaluateJavaScript("window.__campusPet?.layout(\(compact));")
        if taskRingOpen { Task { await refreshTaskRing() } }
        if options.smokeDirectory != nil && !smokeStarted { smokeStarted = true; runSmoke() }
    }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        if (error as NSError).code != NSURLErrorCancelled { receiveAssistantMood(.error) }
    }
    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) { receiveAssistantMood(.error); webView.reload() }
    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = NSAlert(); alert.messageText = message
        alert.addButton(withTitle: "确认"); alert.addButton(withTitle: "取消")
        alert.beginSheetModal(for: assistant) { completionHandler($0 == .alertFirstButtonReturn) }
    }
    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = NSAlert(); alert.messageText = message
        alert.beginSheetModal(for: assistant) { _ in completionHandler() }
    }
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let picker = NSOpenPanel()
        picker.canChooseDirectories = false; picker.allowsMultipleSelection = parameters.allowsMultipleSelection
        picker.allowedContentTypes = [.png, .jpeg, .webP]
        picker.beginSheetModal(for: assistant) { completionHandler($0 == .OK ? picker.urls : nil) }
    }
}
