import AppKit
import WebKit
import Darwin

extension AppDelegate {
    func js(_ body: String) async throws -> Any? {
        do { return try await webView.callAsyncJavaScript(body, arguments: [:], in: nil, contentWorld: .page) }
        catch { throw ServiceError.message("SMOKE main JavaScript: \(body.prefix(180)) · \((error as NSError).userInfo["WKJavaScriptExceptionMessage"] ?? error.localizedDescription)") }
    }

    func waitFor(_ expression: String) async throws {
        print("SMOKE wait: " + expression); fflush(stdout)
        for _ in 0..<160 {
            if (try? await js("return Boolean(\(expression));")) as? Bool == true { return }
            try await Task.sleep(nanoseconds: 150_000_000)
        }
        throw ServiceError.message("原生窗口验收等待超时：\(expression)")
    }

    func clickSmokeButton(_ title: String) async throws {
        let literal = String(data: try JSONSerialization.data(withJSONObject: [title]), encoding: .utf8)!
        let selector = "[...document.querySelectorAll('button')].find(b=>b.getClientRects().length && !b.closest('[inert]') && (b.getAttribute('aria-label')===\(literal)[0] || b.textContent.trim()===\(literal)[0]))"
        try await waitFor(selector)
        _ = try await js(selector + ".click(); return true;")
    }
    func closeSmokeDrawers() async throws {
        _ = try await js("for(const panel of [...document.querySelectorAll('.detail-host:not([hidden])')].reverse())panel.querySelector('header button')?.click(); return true;")
        try await waitFor("!document.querySelector('.workspace-shell')?.inert")
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
            return true;
            """)
        try await waitFor("document.querySelector('.composer .workspace-button')?.disabled === false")
        _ = try await js("document.querySelector('.composer .workspace-button').click(); return true;")
    }

    func runSmoke() {
        if CommandLine.arguments.contains("--record-demo") { prepareRecordedDemo(); return }
        showAssistant(page: "助手")
        Task {
            do {
                guard let output = options.smokeDirectory else { return }
                try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
                try await waitFor("document.querySelector('.composer textarea')")
                guard trusted(webView.url), !trusted(URL(string: "https://example.com")) else {
                    throw ServiceError.message("原生窗口导航边界无效")
                }
                try await verifyDockLifecycle(output: output)
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
                try await clickSmokeButton("学习偏好")
                try await waitFor("document.querySelector('[aria-label=用户偏好与精力档案]')")
                showAssistant(page: "目标与复盘")
                try await waitFor("document.querySelector('[aria-label=长期目标]')")
                try await clickSmokeButton("复盘")
                try await waitFor("document.querySelector('[aria-label=每周复盘]')")
                showAssistant(page: "助手")
                try await waitFor("document.querySelector('.composer textarea')")
                let label = try await js("return document.body.dataset.petLayout;")
                guard label as? String == "full",webView.bounds.width > 640 else { throw ServiceError.message("新的完整窗口默认值未生效") }
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
                // Restoring the target conversation is asynchronous. A draft
                // panel may render before its current approval has loaded.
                try await waitFor("[...document.querySelectorAll('.confirm button')].some(b => b.textContent.trim() === '批准并执行' && !b.disabled)")
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
                try await verifyPetActions(output: output)
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
                try await verifyPetBubbles(output: output)
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
                // A second independent native connection checks the same backend.
                try await service.verifyHealth()
                try await verifyScheduleReminder(output: output)
                try await stopBackend()
                guard !ready else { throw ServiceError.message("停止后台后仍标记为已连接") }
                finishSmoke(error: nil)
            } catch {
                if let output = options.smokeDirectory {
                    let diagnostic = try? await js("return {url:location.pathname,text:document.body.innerText,headings:[...document.querySelectorAll('h1,h2')].map(n=>n.textContent)};")
                    if let diagnostic, let data = try? JSONSerialization.data(withJSONObject: diagnostic, options: [.prettyPrinted]) {
                        try? data.write(to: output.appendingPathComponent("failure-dom.json"))
                    }
                    let runs=try? await js("""
                        const threads=await(await fetch('/api/agent/threads')).json();
                        return await Promise.all(threads.map(async t=>{const runs=await(await fetch('/api/agent/threads/'+t.id+'/runs')).json();return {thread:t.id,runs:await Promise.all(runs.map(async r=>{const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),1500);try{return {run:r,events:await(await fetch('/api/agent/runs/'+r.id+'/events?after=0',{signal:controller.signal})).text()}}catch{return {run:r}}finally{clearTimeout(timeout)}}))}}));
                        """)
                    if let runs,let data=try? JSONSerialization.data(withJSONObject:runs,options:[.prettyPrinted]){try? data.write(to:output.appendingPathComponent("failure-agent.json"))}
                    if let image = try? await webView.takeSnapshot(configuration: nil) { try? saveImage(image, to: output.appendingPathComponent("failure.png")) }
                }
                finishSmoke(error: error.localizedDescription)
            }
        }
    }

    func waitForNative(_ reason: String, _ predicate: () -> Bool) async throws {
        for _ in 0..<100 {
            if predicate() { return }
            try await Task.sleep(nanoseconds: 100_000_000)
        }
        throw ServiceError.message("原生待办验收超时：" + reason + "；open=\(taskRingOpen), pending=\(completingTasks), completed=\(completedTaskIDs), selection=\(todoSelection ?? "nil"), error=\(todoError ?? "nil")")
    }

    func saveTaskRing(to output:URL,name:String) async throws {
        guard let todoPanel else {throw ServiceError.message("缺少单个待办面板")}
        let image=try await todoPanel.renderer.takeSnapshot(configuration:nil)
        try saveImage(image,to:output.appendingPathComponent(name))
    }
    func todoJS(_ code:String) async throws -> Any? {
        guard let todoPanel else {throw ServiceError.message("待办窗口尚未创建")}
        do { return try await todoPanel.renderer.callAsyncJavaScript(code,arguments:[:],in:nil,contentWorld:.page) }
        catch { throw ServiceError.message("SMOKE todo JavaScript: \(code.prefix(180)) · \((error as NSError).userInfo["WKJavaScriptExceptionMessage"] ?? error.localizedDescription)") }
    }
    func waitForTodo(_ expression:String) async throws {
        for _ in 0..<100 {if (try? await todoJS("return Boolean("+expression+")")) as? Bool == true{return};try await Task.sleep(nanoseconds:100_000_000)}
        throw ServiceError.message("原生待办界面超时："+expression)
    }
    func verifyPetBubbles(output:URL) async throws {
        _=try await js("""
            const token=(await(await fetch('/api/csrf')).json()).csrf_token;
            const r=await fetch('/__test__/task-ring',{method:'POST',headers:{'X-CSRF-Token':token}});if(!r.ok)throw new Error(await r.text());return r.json();
            """)
        closePanel();hidePetBubbles();pet.mood = .approval
        let origin=panel.frame.origin
        defer {hidePetBubbles();panel.setFrameOrigin(origin)}
        let visible=panel.screen!.visibleFrame
        panel.setFrameOrigin(NSPoint(x:visible.midX-95,y:visible.midY-120))
        precondition(todoPanel?.isVisible != true)
        _=pet.accessibilityPerformPress()
        try await waitForNative("八项任务在单个面板") {!loadingTaskRing && todayTasks.count==8 && todoPanel?.isVisible == true}
        try await waitForTodo("document.querySelectorAll('.row').length===8")
        guard !assistant.isVisible,taskRingOpen,todoPanel!.frame.size == NSSize(width:328,height:360),visible.contains(todoPanel!.frame),todayTasks.first?.blocks.count==2 else {throw ServiceError.message("待办窗口几何或真实筛选不符")}
        try await saveTaskRing(to:output,name:"pet-todos-real.png")
        let number=todoPanel!.windowNumber
        let internalClick=NSEvent.mouseEvent(with:.leftMouseDown,location:NSPoint(x:120,y:330),modifierFlags:[],timestamp:ProcessInfo.processInfo.systemUptime,windowNumber:number,context:nil,eventNumber:0,clickCount:1,pressure:0)!
        NSApp.postEvent(internalClick,atStart:false)
        let internalUp=NSEvent.mouseEvent(with:.leftMouseUp,location:NSPoint(x:120,y:330),modifierFlags:[],timestamp:ProcessInfo.processInfo.systemUptime,windowNumber:number,context:nil,eventNumber:1,clickCount:1,pressure:0)!
        NSApp.postEvent(internalUp,atStart:false);try await Task.sleep(nanoseconds:100_000_000)
        guard taskRingOpen else {throw ServiceError.message("内部点击误关闭")}
        _=pet.accessibilityPerformPress()
        guard !taskRingOpen,todoPanel?.isVisible == false,bubbleLocalMonitor == nil,bubbleGlobalMonitor == nil else {throw ServiceError.message("重复点击未收起或未清理监视器")}
        _=pet.accessibilityPerformPress();try await waitForNative("重开列表") {!loadingTaskRing && todayTasks.count==8}
        try await waitForTodo("document.querySelectorAll('.row').length===8")
        // Delayed A must never overwrite B, and a closed panel must stay closed.
        _=try await js("""
            window.__todoOriginalFetch=window.fetch;
            window.__todoDelay=true;window.__todoOffline=false;window.__todoMissing=false;window.__todoWrites=0;
            window.fetch=async(input,init)=>{const url=String(input);if(init?.method==='PATCH'&&url.endsWith('ring-task-0'))window.__todoWrites++;
              if(url.endsWith('ring-task-0')&&window.__todoDelay)await new Promise(r=>setTimeout(r,350));
              if(url.endsWith('ring-task-7')&&init?.method==='PATCH'&&window.__todoOffline){await new Promise(r=>setTimeout(r,250));throw new Error('模拟离线')};
              if(url.endsWith('ring-task-1')&&!init?.method&&window.__todoMissing)return new Response('{}',{status:404});
              return window.__todoOriginalFetch(input,init)};return true;
            """)
        showTaskDetails(todayTasks.first{$0.id=="ring-task-0"}!);showTaskDetails(todayTasks.first{$0.id=="ring-task-1"}!)
        try await waitForNative("B详情先返回") {todoDetail?["title"] as? String == "英语阅读"}
        try await Task.sleep(nanoseconds:450_000_000)
        guard todoSelection=="ring-task-1",todoDetail?["title"] as? String == "英语阅读" else{throw ServiceError.message("旧A覆盖B")}
        showTaskDetails(todayTasks.first{$0.id=="ring-task-0"}!);hidePetBubbles();try await Task.sleep(nanoseconds:450_000_000)
        guard !taskRingOpen,todoPanel?.isVisible == false,todoDetail==nil else{throw ServiceError.message("关闭后旧结果重新弹出")}
        _=pet.accessibilityPerformPress();try await waitForNative("旧请求后重开") {!loadingTaskRing && todayTasks.count==8}
        _=try await js("window.__todoDelay=false;window.__todoMissing=true;return true")
        showTaskDetails(todayTasks.first{$0.id=="ring-task-1"}!)
        try await waitForNative("404明确反馈") {todoError?.contains("已删除") == true}
        _=try await js("window.__todoMissing=false;window.__todoOffline=true;return true")
        handleTodoAction("back",id:nil);completeTaskBubble("ring-task-7")
        try await waitForNative("离线保持任务并可重试") {!completingTasks.contains("ring-task-7") && todoError?.contains("模拟离线") == true}
        guard !completedTaskIDs.contains("ring-task-7") else{throw ServiceError.message("离线误完成")}
        completeTaskBubble("ring-task-7");hidePetBubbles();_=pet.accessibilityPerformPress()
        try await waitForNative("旧完成失败后重开仍会刷新") {!completingTasks.contains("ring-task-7") && !loadingTaskRing && todayTasks.count==8}
        _=try await js("window.__todoOffline=false;return true")
        handleTodoAction("back",id:nil)
        try await waitForTodo("document.querySelectorAll('.row').length===8")
        _=try await todoJS("document.querySelector('.row button').click();return true")
        try await waitForTodo("document.querySelector('.detail')?.textContent.includes('任务要求验收')")
        guard taskRingOpen,todoPanel!.windowNumber==number,!assistant.isVisible else {throw ServiceError.message("详情必须留在同一面板")}
        try await saveTaskRing(to:output,name:"pet-detail-real.png")
        _=try await todoJS("document.querySelector('footer button').click();return true")
        try await waitFor("document.querySelector('.detail-panel[aria-label=高数习题]') && !document.querySelector('.detail-panel[aria-label=高数习题]').closest('[hidden]')")
        guard requestedTaskID=="ring-task-0" else{throw ServiceError.message("原生精确任务ID丢失")}
        closePanel();_=pet.accessibilityPerformPress();try await waitForNative("精确跳转后重开") {!loadingTaskRing && todayTasks.count==8}
        // Simulate a slow renderer in this isolated smoke fixture; native state
        // can settle before the visible controls are committed by WebKit.
        _=try await todoJS("window.__smokeRenderTodo=window.renderTodo;window.renderTodo=s=>{const render=window.__smokeRenderTodo;setTimeout(()=>render(s),250)};return true")
        showTaskDetails(todayTasks.first{$0.id=="ring-task-0"}!)
        try await waitForNative("恢复同面板详情") {todoDetail != nil}
        try await waitForTodo("document.querySelector('.detail h3')?.textContent.includes('高数习题') && document.querySelector('.detail button')")
        _=try await todoJS("window.renderTodo=window.__smokeRenderTodo;delete window.__smokeRenderTodo;return true")
        _=try await todoJS("document.querySelector('.detail button').click();return true")
        try await waitForTodo("document.querySelectorAll('.row').length===8")
        _=try await todoJS("const c=document.querySelector('.row input');c.click();c.click();return true")
        try await waitForNative("完成只保存一次") {!completingTasks.contains("ring-task-0") && completedTaskIDs.contains("ring-task-0")}
        let writes=try await js("return window.__todoWrites")
        guard writes as? Int == 1 else{throw ServiceError.message("重复勾选发出多次请求")}
        let saved=try await js("return await(await fetch('/api/tasks/ring-task-0')).json()") as? [String:Any]
        guard (saved?["data"] as? [String:Any])?["status"] as? String == "completed",saved?["revision"] as? Int == 2 else {throw ServiceError.message("完成未真实持久化或重复写入")}
        _=try await js("""
            const t=await(await fetch('/api/tasks/ring-task-1')).json(),token=(await(await fetch('/api/csrf')).json()).csrf_token;
            const r=await fetch('/api/tasks/'+t.id,{method:'PATCH',headers:{'Content-Type':'application/json','X-CSRF-Token':token,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({revision:t.revision,priority:3})});if(!r.ok)throw new Error(await r.text());return true;
            """)
        completeTaskBubble("ring-task-1")
        try await waitForNative("409保留并刷新版本") {!completingTasks.contains("ring-task-1") && todoError != nil && todayTasks.first(where:{$0.id=="ring-task-1"})?.revision==2}
        guard !completedTaskIDs.contains("ring-task-1") else {throw ServiceError.message("版本冲突误完成")}
        while let task=todayTasks.first(where:{!completedTaskIDs.contains($0.id)}) {completeTaskBubble(task.id);try await waitForNative("依次完成"+task.id) {!completingTasks.contains(task.id) && completedTaskIDs.contains(task.id)}}
        hidePetBubbles();_=pet.accessibilityPerformPress();try await waitForNative("重开按真实筛选为空") {!loadingTaskRing && todayTasks.isEmpty}
        try await waitForTodo("document.querySelector('#body').textContent.includes('今天没有待办安排')")
        let untouched=try await js("return(await(await fetch('/api/tasks')).json()).filter(t=>['ring-task-8','ring-task-9','ring-task-11'].includes(t.id)).every(t=>t.data.status==='open')")
        guard untouched as? Bool == true else {throw ServiceError.message("错误完成未来或仅截止任务")}
        pet.onDragStart?();guard !taskRingOpen else {throw ServiceError.message("拖动未收起")}
        _=pet.accessibilityPerformPress();hidePet();guard !taskRingOpen else {throw ServiceError.message("隐藏未收起")}
        showPet();_=pet.accessibilityPerformPress()
        let esc=NSEvent.keyEvent(with:.keyDown,location:.zero,modifierFlags:[],timestamp:ProcessInfo.processInfo.systemUptime,windowNumber:todoPanel!.windowNumber,context:nil,characters:"\u{1b}",charactersIgnoringModifiers:"\u{1b}",isARepeat:false,keyCode:53)!
        NSApp.postEvent(esc,atStart:false);try await waitForNative("Esc关闭") {!taskRingOpen}
        showAssistant(page:"日程");_=pet.accessibilityPerformPress()
        let outside=NSEvent.mouseEvent(with:.leftMouseDown,location:NSPoint(x:2,y:2),modifierFlags:[],timestamp:ProcessInfo.processInfo.systemUptime,windowNumber:assistant.windowNumber,context:nil,eventNumber:0,clickCount:1,pressure:0)!
        NSApp.postEvent(outside,atStart:false);try await waitForNative("外点关闭") {!taskRingOpen}
        closePanel();pet.mood = .idle
        _=try await js("window.fetch=window.__todoOriginalFetch;return true")
        try await verifyTodoVisuals(output:output)
    }

    func verifyTodoVisuals(output:URL) async throws {
        // Fixed synthetic fixture only in the isolated smoke binary path; production data is untouched.
        timer?.invalidate();timer=nil;reminderTimer?.invalidate();reminderTimer=nil
        hidePetBubbles()
        let origin=panel.frame.origin
        defer {
            hidePetBubbles();panel.setFrameOrigin(origin)
            timer=Timer.scheduledTimer(withTimeInterval:1.0/60,repeats:true){[weak self] _ in MainActor.assumeIsolated{self?.animate()}}
            reminderTimer=Timer.scheduledTimer(withTimeInterval:15,repeats:true){[weak self] _ in Task{@MainActor in await self?.refreshReminders();await self?.refreshTaskRing()}}
        }
        if let root=Bundle.main.resourceURL?.appendingPathComponent("NaiWa") {pet.configureAssetPack(try PetAssetPack.load(from:root))}
        pet.mood = .idle;pet.stopAction();pet.display()
        let visible=panel.screen!.visibleFrame
        let canvas=NSRect(x:visible.midX-640,y:visible.midY-235,width:1280,height:470)
        let imageRect=pet.assetGeometry!.imageRect
        panel.setFrameOrigin(NSPoint(x:canvas.minX+723.5-imageRect.minX,y:canvas.minY+50.1666666667-imageRect.minY))
        positionTodoPanel();todoPanel?.makeKeyAndOrderFront(nil)
        try await waitForNative("待办渲染器就绪") {todoPanel?.rendererReady == true}
        let tasks:[[String:Any]]=[
            ["id":"math","title":"高数 · 第三章习题","time":"14:00"],
            ["id":"report","title":"数据结构实验报告","time":"16:00"],
            ["id":"english","title":"英语听力练习","time":"16:20"],
            ["id":"physics","title":"物理实验预习","time":"19:00"]]
        func capture(_ name:String,includeTodo:Bool,petX:CGFloat) async throws {
            panel.setFrameOrigin(NSPoint(x:canvas.minX+petX-imageRect.minX,y:panel.frame.minY))
            if includeTodo {_=try await todoJS("await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));return true")}
            let snapshot=includeTodo ? try await todoPanel!.renderer.takeSnapshot(configuration:nil) : nil
            guard let bitmap=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:1280,pixelsHigh:470,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0),let context=NSGraphicsContext(bitmapImageRep:bitmap),let petBitmap=pet.bitmapImageRepForCachingDisplay(in:pet.bounds) else{throw ServiceError.message("逻辑尺寸原生截图失败")}
            pet.cacheDisplay(in:pet.bounds,to:petBitmap)
            NSGraphicsContext.saveGraphicsState();NSGraphicsContext.current=context
            NSColor(srgbRed:237/255,green:240/255,blue:244/255,alpha:1).setFill();NSRect(x:0,y:0,width:1280,height:470).fill()
            if let snapshot {let frame=todoPanel!.frame;snapshot.draw(in:NSRect(x:frame.minX-canvas.minX,y:frame.minY-canvas.minY,width:frame.width,height:frame.height))}
            let petImage=NSImage(size:pet.bounds.size);petImage.addRepresentation(petBitmap)
            petImage.draw(in:NSRect(x:panel.frame.minX-canvas.minX,y:panel.frame.minY-canvas.minY,width:panel.frame.width,height:panel.frame.height),from:.zero,operation:.sourceOver,fraction:1)
            context.flushGraphics();NSGraphicsContext.restoreGraphicsState()
            try bitmap.representation(using:.png,properties:[:])!.write(to:output.appendingPathComponent(name))
        }
        todoPanel?.render(PetTodoPanelState(payload:["status":"list","tasks":tasks]))
        try await waitForTodo("document.querySelectorAll('.row').length===4")
        try await Task.sleep(nanoseconds:120_000_000)
        try await capture("pet-todos.png",includeTodo:true,petX:723.5)
        todoPanel?.render(PetTodoPanelState(payload:["status":"list","tasks":tasks,"selected":"math","detail":["title":"高数 · 第三章习题","course":"高等数学","time":"14:00","estimate":"45 分钟","due":"今天 18:00","requirements":"完成第三章第 1–8 题，并整理两道错题。"]]))
        try await waitForTodo("document.querySelector('.detail h3')?.textContent==='高数 · 第三章习题'")
        try await Task.sleep(nanoseconds:120_000_000)
        try await capture("pet-detail.png",includeTodo:true,petX:723.5)
        hidePetBubbles();try await capture("pet-idle.png",includeTodo:false,petX:543.5)
        try JSONSerialization.data(withJSONObject:["fixture":"synthetic; actual native NSPanel/WKWebView and original fixed idle PNG","logicalSize":[1280,470],"panelSize":[328,360],"physicalDisplaysTested":1],options:[.prettyPrinted,.sortedKeys]).write(to:output.appendingPathComponent("pet-visual.json"))
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
            // Flush React input state even when macOS occludes the test window.
            await new Promise(resolve => setTimeout(resolve, 0));
            const input = document.querySelector('[data-after-class-form] textarea');
            Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(input, '完成第三章习题 1～5');
            input.dispatchEvent(new Event('input', {bubbles:true}));
            // Flush React input state even when macOS occludes the test window.
            await new Promise(resolve => setTimeout(resolve, 0));
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
        // The fixture writes settings directly, so wait for React Query to refresh.
        showAssistant(page: "设置")
        try await clickSmokeButton("课程与学期")
        try await waitFor("document.querySelector('[name=week1_monday]')?.value === '2026-10-12'")
        showAssistant(page: "课表")
        try await waitFor("document.querySelector('.fc')")
        _ = try await js("window.dispatchEvent(new CustomEvent('campus-timetable-focus', {detail:'2026-10-15T09:00:00+08:00'})); return true;")
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
        try await closeSmokeDrawers()
        _ = try await js("[...document.querySelectorAll('.fc-event')].find(e=>e.textContent.includes('空白格验收课程')).click(); return true;")
        try await waitFor("document.querySelector('[aria-label=日程详情]')")
        let preserved = try await js("return !document.querySelector('.course-slot-dialog') && [...document.querySelectorAll('button')].some(b=>b.textContent==='导入课表');")
        guard preserved as? Bool == true else { throw ServiceError.message("原课程详情或手动入口未保留") }
        try await closeSmokeDrawers()
        try await clickSmokeButton("导入课表")
        try await clickSmokeButton("文字导入")
        try await clickSmokeButton("手工添加课程")
        try await waitFor("[...document.querySelectorAll('h2')].some(e=>e.textContent==='添加一门课程')")
        let saved = try await webView.takeSnapshot(configuration: nil)
        try saveImage(saved, to: output.appendingPathComponent("course-cell-saved.png"))
    }

    func verifyPetActions(output: URL) async throws {
        pet.mood = .idle; pet.reducedMotion = false; pet.animationsVisible = true
        guard !pet.availableActions.isEmpty else { throw ServiceError.message("新角色动作未安装") }
        for action in pet.availableActions {
            guard pet.playAction(action.id), let clip = pet.assetClip else { throw ServiceError.message("清单动作加载失败") }
            let firstDuration = Double(clip.frames[0].durationNanoseconds) / 1e9
            if clip.frames.count > 1 {
                pet.advanceAnimation(by: firstDuration + 0.000001)
                guard pet.assetFrameIndex == 1 else { throw ServiceError.message("素材原始时序未保留") }
            }
            guard let bitmap = pet.bitmapImageRepForCachingDisplay(in: pet.bounds), let geometry = pet.assetGeometry else { throw ServiceError.message("素材绘制失败") }
            pet.cacheDisplay(in: pet.bounds, to: bitmap)
            var hits = 0
            for y in stride(from: 0, to: 560, by: 8) {
                for x in stride(from: 0, to: 420, by: 8) {
                    let rect = geometry.viewRect(fromSource: NSRect(x:x,y:y,width:1,height:1))
                    if pet.isInteractive(NSPoint(x:rect.midX,y:rect.midY)) { hits += 1 }
                }
            }
            guard hits > 40, !pet.isInteractive(NSPoint(x:1,y:1)), pet.assetCacheBytes <= 64 * 1024 * 1024 else { throw ServiceError.message("新素材命中或缓存上限失败") }
            try bitmap.representation(using:.png,properties:[:])!.write(to:output.appendingPathComponent("action-"+action.id+".png"))
            pet.advanceAnimation(by: 100)
            guard !pet.hasActiveAction, pet.assetClipName == "idle" else { throw ServiceError.message("动作结束未回到当前状态") }
        }
        pet.playAction(pet.availableActions[0].id); pet.mood = .approval
        guard !pet.hasActiveAction else { throw ServiceError.message("审批未打断表演") }
        try await waitForNative("随机表演测试等待鼠标释放") {NSEvent.pressedMouseButtons == 0}
        pet.mood = .idle; automaticActions = true; nextPerformanceAt = 0; animate()
        if !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion { guard pet.hasActiveAction else { throw ServiceError.message("空闲表演未启动：mouse=\(NSEvent.pressedMouseButtons), visible=\(panel.isVisible), todo=\(taskRingOpen), reminder=\(pet.reminderText != nil), sleeping=\(sleeping)") } }
        let decoded = pet.decodedFrameCount
        hidePet(); animate()
        guard pet.decodedFrameCount == decoded else { throw ServiceError.message("隐藏后仍解码") }
        showPet(); pet.stopAction(); pet.mood = .thinking; nextPerformanceAt = 0; animate()
        guard !pet.hasActiveAction else { throw ServiceError.message("忙碌时随机表演") }
        pet.mood = .sleeping; let index = pet.assetFrameIndex; pet.advanceAnimation(by:1)
        guard pet.assetFrameIndex == index else { throw ServiceError.message("休息仍在播放") }
        pet.mood = .idle; pet.reducedMotion = true; pet.advanceAnimation(by:1)
        guard !pet.hasActiveAction else { throw ServiceError.message("减少动态效果仍有表演") }
        pet.reducedMotion = false; automaticActions = false
        for state in [PetMood.starting,.idle,.thinking,.replying,.approval,.error,.sleeping] {
            pet.mood = state
            if let bitmap = pet.bitmapImageRepForCachingDisplay(in:pet.bounds) {
                pet.cacheDisplay(in:pet.bounds,to:bitmap)
                try bitmap.representation(using:.png,properties:[:])!.write(to:output.appendingPathComponent("state-"+state.rawValue+".png"))
            }
        }
        pet.mood = .idle
        var peakCache = pet.assetCacheBytes
        if pet.availableActions.contains(where:{$0.id == "surprised"}) {
            guard pet.playAction("surprised") else { throw ServiceError.message("惊讶动作未启动") }
            for _ in 0..<75 {
                try await Task.sleep(nanoseconds:100_000_000)
                pet.displayIfNeeded(); peakCache = max(peakCache,pet.assetCacheBytes)
                guard peakCache <= 64*1024*1024 else { throw ServiceError.message("实时播放缓存越界") }
            }
            guard !pet.hasActiveAction else { throw ServiceError.message("实时播放未正常结束") }
        }
        let start = ProcessInfo.processInfo.systemUptime, cpu = clock()
        try await Task.sleep(nanoseconds:3_000_000_000)
        let wall = ProcessInfo.processInfo.systemUptime-start
        let profile:[String:Any] = ["measurement":"3-second real-time native process idle playback; excludes separate WebKit process", "wall_seconds":wall, "native_cpu_seconds":Double(clock()-cpu)/Double(CLOCKS_PER_SEC), "cache_bytes":pet.assetCacheBytes, "peak_cache_bytes":peakCache, "cache_limit_bytes":64*1024*1024, "decoded_frames":pet.decodedFrameCount, "canvas":[420,560]]
        try JSONSerialization.data(withJSONObject:profile,options:[.prettyPrinted,.sortedKeys]).write(to:output.appendingPathComponent("pet-playback-profile.json"))
    }

    func verifyScheduleReminder(output: URL) async throws {
        let identifier = try await js("""
            const token = (await (await fetch('/api/csrf')).json()).csrf_token;
            const start = new Date(Date.now()+240000), end = new Date(start.getTime()+3600000);
            const r = await fetch('/api/fixed-events', {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':token,'Idempotency-Key':crypto.randomUUID()}, body:JSON.stringify({title:'紫色提醒验收',starts_at:start.toISOString(),ends_at:end.toISOString()})});
            if(!r.ok) throw new Error(await r.text());
            const event = await r.json();
            window.__reminderFixture = {event_id:event.id,starts_at:start.toISOString(),revision:0,enabled:true,target_kind:'file',target:'/tmp/验收文件.pdf'};
            const saved=await fetch('/api/schedule-shortcut',{method:'PUT',headers:{'Content-Type':'application/json','X-CSRF-Token':token},body:JSON.stringify(window.__reminderFixture)});
            if(!saved.ok) throw new Error(await saved.text());
            window.__reminderFixture.revision=(await saved.json()).revision;
            return event.id;
            """)
        guard identifier is String else { throw ServiceError.message("提醒验收日程创建失败") }
        await refreshReminders()
        guard pendingReminders.contains(where: { $0.title == "紫色提醒验收" }), pet.reminderText != nil,
              !pet.isInteractive(NSPoint(x:15,y:200)) else {
            throw ServiceError.message("提醒状态或透明穿透未生效")
        }
        guard !taskRingOpen else {throw ServiceError.message("提醒不能自动弹出待办")}
        _=pet.accessibilityPerformPress();try await waitForTodo("document.querySelector('#review')?.textContent==='待确认'")
        hidePetBubbles()
        guard let bitmap = pet.bitmapImageRepForCachingDisplay(in: pet.bounds) else { throw ServiceError.message("提醒截图失败") }
        pet.cacheDisplay(in: pet.bounds, to: bitmap)
        try bitmap.representation(using:.png,properties:[:])!.write(to:output.appendingPathComponent("reminder-purple.png"))
        _ = try await js("""
            const token=(await (await fetch('/api/csrf')).json()).csrf_token;
            const r=await fetch('/api/schedule-shortcut',{method:'PUT',headers:{'Content-Type':'application/json','X-CSRF-Token':token},body:JSON.stringify({...window.__reminderFixture,enabled:false})});
            if(!r.ok) throw new Error(await r.text()); return true;
            """)
        await refreshReminders()
        guard !pendingReminders.contains(where: { $0.title == "紫色提醒验收" }), pet.reminderText == nil else {
            throw ServiceError.message("关闭提醒后未恢复原形象")
        }
    }

    func verifyDockLifecycle(output: URL) async throws {
        guard NSApp.activationPolicy() == .regular,
              NSRunningApplication.current.activationPolicy == .regular,
              (Bundle.main.object(forInfoDictionaryKey: "LSUIElement") as? Bool) != true,
              NSRunningApplication.current.icon != nil else {
            throw ServiceError.message("应用未注册为带Dock图标的普通应用")
        }
        assistant.performClose(nil)
        hidePet()
        guard !assistant.isVisible, !panel.isVisible,
              NSApp.activationPolicy() == .regular,
              !applicationShouldTerminateAfterLastWindowClosed(NSApp),
              statusItem.button != nil else {
            throw ServiceError.message("窗口全部隐藏后应保留Dock和菜单栏入口")
        }
        try await service.verifyHealth()
        guard applicationShouldHandleReopen(NSApp, hasVisibleWindows: false),
              assistant.isVisible, panel.isVisible else {
            throw ServiceError.message("Dock重开未恢复主窗口和桌宠")
        }
        let checks: [String: Any] = ["passed": true, "regular_activation_policy": true,
            "normal_app_bundle": true, "application_icon_available": true,
            "all_windows_hidden_keeps_dock_and_service": true,
            "reopen_callback_restores_both_windows": true,
            "menu_bar_retained": true,
            "scope": "actual AppKit lifecycle; system reopen delegate invoked; no physical Dock click automation"]
        try JSONSerialization.data(withJSONObject: checks, options: [.prettyPrinted, .sortedKeys])
            .write(to: output.appendingPathComponent("dock-lifecycle.json"))
    }

    func finishSmoke(error: String?) {
        if let output = options.smokeDirectory {
            try? FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
            let healthEncoder = JSONEncoder()
            healthEncoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            if let health = try? healthEncoder.encode(service.healthDiagnostics) {
                try? health.write(to: output.appendingPathComponent("health-diagnostics.json"))
            }
            let assetURL = Bundle.main.resourceURL?.appendingPathComponent("NaiWa/asset-pack.json")
            let assetData = assetURL.flatMap { try? Data(contentsOf:$0) }
            let assetInfo = assetData.flatMap { (try? JSONSerialization.jsonObject(with:$0)) as? [String:Any] }
            let result: [String: Any] = ["qa_asset_fixture": assetInfo?["qa_fixture"] as? Bool ?? false, "passed": error == nil, "error": error ?? "", "scope": "native AppKit/WebKit + real Deep Agents with explicit test model + isolated real SQLite/API; no paid model calls; unrelated global desktop clicks ignored in smoke only, controlled outside event tested", "checks": ["regular Dock application persists while all windows hidden and restores on reopen", "local session", "chat composer", "real draft confirmation", "task/settings navigation", "preference profile entry", "goals and weekly review entry", "full window default and narrow left navigation", "streaming chat", "busy backend rejects native shutdown", "natural-language draft", "no task write before approval", "real graph interrupt and approval", "persisted agent state animation bridge", "approval across page navigation", "paused state retains approval", "after-class opening dialog", "homework form to real calendar blocks", "no repeated completed check-in", "blank calendar cell defaults", "cancel course without draft", "course approval before save", "saved course calendar rendering", "existing event details", "original manual course entry", "manifest actions and original frame timing", "bounded lazy frame cache", "animated alpha hit testing", "action pause and reduced motion", "idle random performance", "no random action while busy", "hidden animation suspension", "pause/resume", "hide/restore", "screen bounds", "panel close", "native snapshots", "exit submenu", "cancel shutdown", "shared web backend health", "authenticated graceful backend shutdown", "silent purple schedule reminder", "reminder stays accessible inside todo panel", "disabled reminder restores original character", "pet click opens a single today todo panel", "scheduled tasks only and task deduplication", "all tasks scroll in one 328x360 panel", "repeat click collapses todo panel", "same panel reads current task details and steps", "explicit checkbox persists completion once", "completion synchronizes existing task UI", "completed rows stay struck through until reopen", "revision conflict retains task and reloads", "complete remaining tasks and empty state", "future and due-only tasks remain unchanged", "drag and hide collapse todo panel", "outside click collapses todo panel"]]
            if let data = try? JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted, .sortedKeys]) {
                try? data.write(to: output.appendingPathComponent("result.json"))
            }
        }
        bypassServiceShutdownOnTerminate = true
        NSApp.terminate(nil)
    }
}
