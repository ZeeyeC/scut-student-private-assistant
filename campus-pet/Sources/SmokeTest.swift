import AppKit
import WebKit

extension AppDelegate {
    func js(_ body: String) async throws -> Any? {
        try await webView.callAsyncJavaScript(body, arguments: [:], in: nil, contentWorld: .page)
    }

    func waitFor(_ expression: String) async throws {
        for _ in 0..<160 {
            if (try? await js("return Boolean(\(expression));")) as? Bool == true { return }
            try await Task.sleep(nanoseconds: 150_000_000)
        }
        throw ServiceError.message("原生窗口验收等待超时：\(expression)")
    }

    func waitForMood(_ mood: PetMood) async throws {
        for _ in 0..<100 {
            if pet.mood == mood { return }
            try await Task.sleep(nanoseconds: 100_000_000)
        }
        throw ServiceError.message("桌宠状态同步超时：\(mood.rawValue)，当前 \(pet.mood.rawValue)")
    }

    func saveImage(_ image: NSImage, to url: URL) throws {
        guard let tiff = image.tiffRepresentation, let bitmap = NSBitmapImageRep(data: tiff),
              let png = bitmap.representation(using: .png, properties: [:]) else {
            throw ServiceError.message("截图编码失败")
        }
        try png.write(to: url)
    }

    func sendSmokeMessage(_ message: String) async throws {
        let literal = String(data: try JSONSerialization.data(withJSONObject: [message]), encoding: .utf8)!
        _ = try await js("""
            const input = document.querySelector('.composer textarea');
            Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(input, \(literal)[0]);
            input.dispatchEvent(new Event('input', {bubbles:true}));
            await new Promise(requestAnimationFrame);
            document.querySelector('.composer button').click();
            return true;
            """)
    }

    func runSmoke() {
        showAssistant(page: "助手")
        Task {
            do {
                guard let output = options.smokeDirectory else { return }
                try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
                try await waitFor("document.querySelector('.composer textarea')")
                guard trusted(webView.url), !trusted(URL(string: "https://example.com")) else {
                    throw ServiceError.message("原生窗口导航边界无效")
                }
                // Uses an isolated real database, never a user's model or school account.
                let created = try await js("""
                    const token = (await (await fetch('/api/csrf')).json()).csrf_token;
                    const post = async (path, body) => {
                      const r = await fetch('/api' + path, {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':token,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});
                      if (!r.ok) throw new Error(await r.text());
                      return r.json();
                    };
                    const d = await post('/drafts/assignment', {items:[{title:'桌宠验收 · 阅读一篇论文',due_text:'待确认'}]});
                    const saved = await post('/drafts/' + d.id + '/confirm', {revision:d.revision});
                    return saved.saved_ids.length === 1;
                    """)
                guard created as? Bool == true else { throw ServiceError.message("真实业务保存失败") }
                showAssistant(page: "作业")
                try await waitFor("document.body.textContent.includes('桌宠验收 · 阅读一篇论文')")
                showAssistant(page: "设置")
                try await waitFor("document.body.textContent.includes('模型连接')")
                showAssistant(page: "助手")
                try await waitFor("document.querySelector('.composer textarea')")
                let label = try await js("return document.body.dataset.petLayout;")
                guard label as? String == "compact" else { throw ServiceError.message("桌宠紧凑面板未生效") }
                try await sendSmokeMessage("流式测试")
                try await waitFor("document.querySelector('.message.assistant')?.textContent.includes('第一段')")
                try await waitForMood(.replying)
                do {
                    try await stopBackend()
                    throw ServiceError.message("后台忙碌时错误地接受了停止请求")
                } catch {
                    guard error.localizedDescription.contains("仍在处理"), ready, !stoppingService else { throw error }
                }
                try await waitFor("document.querySelector('.message.assistant')?.textContent.includes('第一段第二段')")
                try await waitFor("document.querySelector('.chat-toolbar button')?.disabled === false")
                try await sendSmokeMessage("帮我增加一个任务：明天阅读文献")
                try await waitFor("document.querySelector('.review-panel')?.textContent.includes('核对任务草稿')")
                try await waitFor("document.querySelector('.chat-toolbar button')?.disabled === false")
                let count = try await js("return (await (await fetch('/api/tasks')).json()).length;")
                guard (count as? NSNumber)?.intValue == 1 else { throw ServiceError.message("模型草稿在批准前写入了任务") }
                let pending = try await js("return (await (await fetch('/api/drafts')).json()).find(d => d.data.draft_kind === 'assignment').id;")
                guard let draftID = pending as? String else { throw ServiceError.message("模型未生成真实草稿") }
                try await sendSmokeMessage("commit:" + draftID)
                try await waitFor("document.querySelector('.confirm')?.textContent.includes('批准并执行')")
                try await waitForMood(.approval)
                showAssistant(page: "设置")
                try await waitFor("document.body.textContent.includes('模型连接')")
                try await Task.sleep(nanoseconds: 1_300_000_000)
                guard pet.mood == .approval else { throw ServiceError.message("切换页面后审批状态丢失") }
                toggleSleep()
                try await Task.sleep(nanoseconds: 1_100_000_000)
                guard pet.mood == .sleeping else { throw ServiceError.message("暂停期间状态更新不应唤醒动画") }
                toggleSleep()
                guard pet.mood == .approval else { throw ServiceError.message("恢复后未保留审批状态") }
                showReview()
                try await waitFor("document.querySelector('.review-panel')?.getBoundingClientRect().top < innerHeight / 2")
                let pendingSnapshot = try await webView.takeSnapshot(configuration: nil)
                try saveImage(pendingSnapshot, to: output.appendingPathComponent("approval.png"))
                _ = try await js("[...document.querySelectorAll('.confirm button')].find(b => b.textContent.trim() === '批准并执行').click(); return true;")
                try await waitFor("(await (await fetch('/api/tasks')).json()).length === 2")
                try await waitFor("!document.querySelector('.review-panel')")
                // The real stream and interrupt above verify the bridge. Do not
                // overwrite React-managed status text to simulate a second run.
                try await waitFor("document.querySelector('.chat [role=status]')?.textContent === ''")
                try await verifyAfterClass(output: output)
                try await verifyCourseCell(output: output)
                try verifyVideoActions(output: output)
                toggleSleep()
                guard pet.mood == .sleeping else { throw ServiceError.message("暂停动画失败") }
                toggleSleep()
                hidePet()
                guard !panel.isVisible else { throw ServiceError.message("隐藏失败") }
                showPet()
                let old = panel.frame.origin
                panel.setFrameOrigin(NSPoint(x: -99999, y: -99999))
                constrainAndSave()
                guard NSScreen.screens.contains(where: { $0.visibleFrame.contains(panel.frame) }) else {
                    throw ServiceError.message("屏幕边界约束失败")
                }
                panel.setFrameOrigin(old)
                guard let bitmap = pet.bitmapImageRepForCachingDisplay(in: pet.bounds) else {
                    throw ServiceError.message("桌宠截图失败")
                }
                pet.cacheDisplay(in: pet.bounds, to: bitmap)
                try bitmap.representation(using: .png, properties: [:])!.write(to: output.appendingPathComponent("pet.png"))
                let snapshot = try await webView.takeSnapshot(configuration: nil)
                try saveImage(snapshot, to: output.appendingPathComponent("assistant.png"))
                closePanel()
                guard !assistant.isVisible, panel.isVisible else { throw ServiceError.message("关闭面板不应退出桌宠") }
                // Exercise the real secondary menu and cancel its native sheet.
                guard petMenu().item(withTitle: "关闭与退出")?.submenu?.item(withTitle: "停止后台并退出…") != nil else {
                    throw ServiceError.message("关闭与退出二级菜单缺失")
                }
                stopServiceAndQuit()
                guard let confirmation = exitConfirmation else { throw ServiceError.message("停止服务前没有确认框") }
                confirmation.buttons[1].performClick(nil)
                for _ in 0..<20 where exitConfirmation != nil { try await Task.sleep(nanoseconds: 50_000_000) }
                guard exitConfirmation == nil, !stoppingService, ready else { throw ServiceError.message("取消停止不应退出或改变服务状态") }
                try await service.verifyHealth()
                // A second web session uses the same test backend before shutdown.
                let peer = try await URLSession.shared.data(from: assistantOrigin.appendingPathComponent("api/healthz"))
                guard (peer.1 as? HTTPURLResponse)?.statusCode == 200 else { throw ServiceError.message("共享后台检查失败") }
                try await stopBackend()
                guard !ready else { throw ServiceError.message("停止后台后仍标记为已连接") }
                finishSmoke(error: nil)
            } catch { finishSmoke(error: error.localizedDescription) }
        }
    }

    func verifyAfterClass(output: URL) async throws {
        let seeded = try await js("""
            const token = (await (await fetch('/api/csrf')).json()).csrf_token;
            const write = async (path, body, method = 'POST') => {
              const r = await fetch('/api' + path, {method, headers:{'Content-Type':'application/json','X-CSRF-Token':token,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(body)});
              if (!r.ok) throw new Error(await r.text()); return r.json();
            };
            const settings = await (await fetch('/api/settings')).json();
            settings.data = {...settings.data, week1_monday:'2026-10-12', week_count:20,
              periods:{'1':{start:'09:00',end:'10:00'},'2':{start:'17:00',end:'18:00'}},
              study_windows:[{start:'19:00',end:'23:00'}]};
            await write('/settings', settings, 'PUT');
            const d = await write('/drafts/timetable', {semester_label:'隔离课后作业验收', courses:[
              {source_key:'checkin-math',name:'高等数学',weekday:3,weeks:[1],periods:[1]},
              {source_key:'checkin-physics',name:'大学物理',weekday:3,weeks:[1],periods:[2]}
            ]});
            await write('/drafts/' + d.id + '/confirm', {revision:d.revision});
            // Fixture starts Oct 14; no previously installed/historical reminders.
            window.dispatchEvent(new Event('campus-after-class-open'));
            return true;
            """)
        guard seeded as? Bool == true else { throw ServiceError.message("课后验收课表准备失败") }
        try await waitFor("document.querySelector('[data-after-class-form] select')")
        guard assistant.isVisible else { throw ServiceError.message("课后询问未唤出原生助手面板") }
        let question = try await webView.takeSnapshot(configuration: nil)
        try saveImage(question, to: output.appendingPathComponent("after-class.png"))
        _ = try await js("""
            const selects = document.querySelectorAll('[data-after-class-form] select');
            selects[0].value = 'homework'; selects[0].dispatchEvent(new Event('change', {bubbles:true}));
            selects[1].value = 'none'; selects[1].dispatchEvent(new Event('change', {bubbles:true}));
            await new Promise(requestAnimationFrame);
            const input = document.querySelector('[data-after-class-form] textarea');
            Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(input, '完成第三章习题 1～5');
            input.dispatchEvent(new Event('input', {bubbles:true}));
            await new Promise(requestAnimationFrame);
            const button = [...document.querySelectorAll('[data-after-class-form] button')].find(b => b.textContent === '保存作业并加入日程');
            button.click(); return true;
            """)
        try await waitFor("document.querySelector('[data-after-class-result]')?.textContent.includes('已保存 1 项作业')")
        let result = try await js("""
            const tasks = await (await fetch('/api/tasks')).json();
            const blocks = await (await fetch('/api/plan-blocks')).json();
            const task = tasks.find(t => t.data.title.includes('完成第三章习题'));
            return Boolean(task && blocks.some(b => b.data.task_id === task.id));
            """)
        guard result as? Bool == true else { throw ServiceError.message("课后作业没有真实写入日程") }
        let saved = try await webView.takeSnapshot(configuration: nil)
        try saveImage(saved, to: output.appendingPathComponent("after-class-saved.png"))
        _ = try await js("[...document.querySelectorAll('[role=dialog] button')].find(b=>b.textContent==='完成').click(); return true;")
        try await waitFor("!document.querySelector('[data-after-class-result]')")
        let done = try await js("""
            const token=(await(await fetch('/api/csrf')).json()).csrf_token;
            const r=await fetch('/api/after-class/open',{method:'POST',headers:{'X-CSRF-Token':token,'Content-Type':'application/json'},body:'{}'});
            return !(await r.json()).due;
            """)
        guard done as? Bool == true else { throw ServiceError.message("已填科目不应重复询问") }
    }

    func verifyCourseCell(output: URL) async throws {
        showAssistant(page: "课表")
        try await waitFor("document.querySelector('.fc')")
        _ = try await js("window.dispatchEvent(new CustomEvent('campus-calendar-saved', {detail:'2026-10-15T09:00:00+08:00'})); return true;")
        try await waitFor("document.querySelector('.fc-timeGridWeek-button')")
        _ = try await js("document.querySelector('.fc-timeGridWeek-button').click(); return true;")
        try await waitFor("document.querySelector('.fc-timegrid-col[data-date=\"2026-10-15\"]')")
        let clickCell = """
            const row = document.querySelector('.fc-timegrid-slot[data-time="09:00:00"]');
            row.scrollIntoView({block:'center'});
            const day = document.querySelector('.fc-timegrid-col[data-date="2026-10-15"]');
            const r = row.getBoundingClientRect(), d = day.getBoundingClientRect();
            const x = d.left + d.width / 2, y = r.top + r.height / 2;
            const target = document.elementFromPoint(x,y);
            for (const type of ['mousedown','mouseup','click']) target.dispatchEvent(new MouseEvent(type, {
              bubbles:true, cancelable:true, view:window, clientX:x,clientY:y,button:0,buttons:type==='mousedown'?1:0
            }));
            return true;
            """
        _ = try await js(clickCell)
        try await waitFor("document.querySelector('.course-slot-dialog input[name=name]')")
        let defaults = try await js("""
            const form = document.querySelector('.course-slot-dialog form');
            const values = Object.fromEntries(new FormData(form));
            if (values.weekday !== '4' || values.weeks !== '1' || values.periods !== '1')
              throw new Error('空白格默认值：' + JSON.stringify(values) + '；' + document.querySelector('.course-slot-dialog').textContent);
            return true;
            """)
        guard defaults as? Bool == true else { throw ServiceError.message("空白格未带入正确星期、教学周和节次") }
        let empty = try await webView.takeSnapshot(configuration: nil)
        try saveImage(empty, to: output.appendingPathComponent("course-cell.png"))
        _ = try await js("document.querySelector('.course-slot-dialog header button').click(); return true;")
        try await waitFor("!document.querySelector('.course-slot-dialog')")
        let cancelled = try await js("return !(await (await fetch('/api/drafts')).json()).some(d=>d.data.draft_kind==='timetable');")
        guard cancelled as? Bool == true else { throw ServiceError.message("取消空白格录入不应产生课程草稿") }
        _ = try await js(clickCell)
        try await waitFor("document.querySelector('.course-slot-dialog input[name=name]')")
        _ = try await js("""
            const form = document.querySelector('.course-slot-dialog form');
            form.querySelector('[name=name]').value = '空白格验收课程';
            form.querySelector('[name=location]').value = '教学楼 101';
            form.requestSubmit(); return true;
            """)
        try await waitFor("!document.querySelector('.course-slot-dialog') && document.body.textContent.includes('课表预览')")
        let notSaved = try await js("return !(await (await fetch('/api/courses')).json()).some(c=>c.data.name==='空白格验收课程');")
        guard notSaved as? Bool == true else { throw ServiceError.message("课程在确认前被保存") }
        _ = try await js("[...document.querySelectorAll('button')].find(b=>b.textContent==='校对完成，准备保存').click(); return true;")
        try await waitFor("document.querySelector('.confirm')")
        _ = try await js("[...document.querySelectorAll('.confirm button')].find(b=>b.textContent==='确认保存').click(); return true;")
        try await waitFor("[...document.querySelectorAll('.fc-event')].some(e=>e.textContent.includes('空白格验收课程'))")
        // Existing events must retain their details action instead of opening an add dialog.
        _ = try await js("[...document.querySelectorAll('.fc-event')].find(e=>e.textContent.includes('空白格验收课程')).click(); return true;")
        try await waitFor("document.querySelector('[aria-label=日程详情]')")
        let preserved = try await js("return !document.querySelector('.course-slot-dialog') && [...document.querySelectorAll('button')].some(b=>b.textContent==='手工添加课程');")
        guard preserved as? Bool == true else { throw ServiceError.message("原课程详情或手动入口未保留") }
        _ = try await js("[...document.querySelectorAll('button')].find(b=>b.textContent==='手工添加课程').click(); return true;")
        try await waitFor("[...document.querySelectorAll('h2')].some(e=>e.textContent==='添加一门课程')")
        let saved = try await webView.takeSnapshot(configuration: nil)
        try saveImage(saved, to: output.appendingPathComponent("course-cell-saved.png"))
    }

    func verifyVideoActions(output: URL) throws {
        pet.mood = .idle
        pet.reducedMotion = false
        for action in PetAction.allCases {
            guard pet.play(action), let clip = pet.animation, clip.images.count >= 60 else {
                throw ServiceError.message("视频动作加载失败：\(action.title)")
            }
            pet.advanceAnimation(by: 1)
            guard pet.actionFrameIndex == 20 else { throw ServiceError.message("逐帧动画未按 20 fps 前进") }
            let frame = clip.pixels[pet.actionFrameIndex]
            // Validate actual animated pixels, including raised arms, can receive
            // clicks while transparent corners remain click-through.
            var hits = 0
            for y in stride(from: 0, to: 320, by: 8) {
                for x in stride(from: 0, to: 320, by: 8) where (frame.colorAt(x: x, y: y)?.alphaComponent ?? 0) > 0.5 {
                    let point = NSPoint(x: 10 + (Double(x) + 0.5) / 320 * 170, y: (320 - Double(y) - 0.5) / 320 * 170)
                    if pet.isInteractive(point) { hits += 1 }
                }
            }
            guard hits > 40, !pet.isInteractive(NSPoint(x: 1, y: 1)) else {
                throw ServiceError.message("动画透明命中检测失败：\(action.title)")
            }
            let index = pet.actionFrameIndex
            pet.mood = .sleeping; pet.advanceAnimation(by: 0.5)
            guard pet.actionFrameIndex == index else { throw ServiceError.message("暂停时动作仍在前进") }
            pet.mood = .idle; pet.reducedMotion = true; pet.advanceAnimation(by: 0.5)
            guard pet.actionFrameIndex == index else { throw ServiceError.message("减少动态效果未生效") }
            pet.reducedMotion = false
            if action == .bearShake {
                let onePass = Double(clip.images.count) / clip.fps
                pet.advanceAnimation(by: onePass)
                guard pet.activeAction == action, pet.actionFrameIndex == index,
                      abs(clip.duration - 6.6) < 0.001 else {
                    throw ServiceError.message("狗熊哆嗦毛应原速重复两遍，总时长 6.6 秒")
                }
            }
            if let bitmap = pet.bitmapImageRepForCachingDisplay(in: pet.bounds) {
                pet.cacheDisplay(in: pet.bounds, to: bitmap)
                try bitmap.representation(using: .png, properties: [:])!.write(to: output.appendingPathComponent(action.rawValue + ".png"))
            }
            pet.advanceAnimation(by: clip.duration)
            guard pet.activeAction == nil else { throw ServiceError.message("动作结束未回到待机") }
        }
        automaticActions = true; nextPerformanceAt = 0; animate()
        if !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
            guard pet.activeAction != nil else { throw ServiceError.message("空闲随机表演未启动") }
        }
        let elapsed = pet.actionElapsed
        hidePet(); animate()
        guard pet.actionElapsed == elapsed else { throw ServiceError.message("隐藏后动画仍在运行") }
        showPet(); pet.stopAction()
        pet.mood = .thinking; nextPerformanceAt = 0; animate()
        guard pet.activeAction == nil else { throw ServiceError.message("助手忙碌时不应随机表演") }
        pet.mood = .idle; automaticActions = false
    }

    func finishSmoke(error: String?) {
        if let output = options.smokeDirectory {
            try? FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
            let result: [String: Any] = ["passed": error == nil, "error": error ?? "", "scope": "native AppKit/WebKit + real Deep Agents with explicit test model + isolated real SQLite/API; no paid model calls", "checks": ["local session", "chat composer", "real draft confirmation", "task/settings navigation", "compact layout", "streaming chat", "busy backend rejects native shutdown", "natural-language draft", "no task write before approval", "real graph interrupt and approval", "persisted agent state animation bridge", "approval across page navigation", "paused state retains approval", "after-class opening dialog", "homework form to real calendar blocks", "no repeated completed check-in", "blank calendar cell defaults", "cancel course without draft", "course approval before save", "saved course calendar rendering", "existing event details", "original manual course entry", "three video action assets", "20 fps playback and completion", "animated alpha hit testing", "action pause and reduced motion", "idle random performance", "no random action while busy", "hidden animation suspension", "pause/resume", "hide/restore", "screen bounds", "panel close", "native snapshots", "exit submenu", "cancel shutdown", "shared web backend health", "authenticated graceful backend shutdown"]]
            if let data = try? JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted, .sortedKeys]) {
                try? data.write(to: output.appendingPathComponent("result.json"))
            }
        }
        NSApp.terminate(nil)
    }
}
