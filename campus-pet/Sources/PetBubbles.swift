import AppKit
import WebKit

extension AppDelegate {
    func togglePetBubbles() {
        if taskRingOpen { hidePetBubbles();return }
        guard panel.isVisible else { return }
        taskRingOpen=true;todoSession=UUID();todayTasks=[];completedTaskIDs=[];todoSelection=nil;todoDetail=nil;todoError=nil
        pet.stopAction();scheduleNextPerformance()
        if todoPanel == nil {
            todoPanel=PetTodoPanel()
            todoPanel?.onAction={ [weak self] action,id in self?.handleTodoAction(action,id:id) }
        }
        positionTodoPanel();todoPanel?.render(.loading);todoPanel?.makeKeyAndOrderFront(nil)
        bubbleLocalMonitor=NSEvent.addLocalMonitorForEvents(matching:[.leftMouseDown,.rightMouseDown,.keyDown]) { [weak self] event in
            let consumed=MainActor.assumeIsolated {
                guard let self else {return false}
                if event.type == .keyDown { if event.keyCode == 53 {self.hidePetBubbles();return true} }
                else if event.window !== self.panel && event.window !== self.todoPanel {self.hidePetBubbles()}
                return false
            }
            return consumed ? nil : event
        }
        bubbleGlobalMonitor=NSEvent.addGlobalMonitorForEvents(matching:[.leftMouseDown,.rightMouseDown]) { [weak self] _ in MainActor.assumeIsolated {self?.hidePetBubbles()} }
        Task {await refreshTaskRing()}
    }
    func positionTodoPanel() {
        let visible=panel.screen?.visibleFrame ?? NSScreen.main!.visibleFrame
        let local=pet.visibleCharacterBounds
        let character=panel.convertToScreen(local)
        let side:PetTodoLayout.Side=UserDefaults.standard.string(forKey:"petTodoSide") == "right" ? .right : .left
        todoPanel?.setFrame(PetTodoLayout.frame(near:character,within:visible,preferredSide:side),display:true)
    }
    func hidePetBubbles() {
        taskRingOpen=false;todoSession=UUID();ringGeneration+=1;detailGeneration+=1;loadingTaskRing=false
        todoPanel?.orderOut(nil);todoSelection=nil;todoDetail=nil;todoError=nil
        if let bubbleLocalMonitor {NSEvent.removeMonitor(bubbleLocalMonitor)}
        if let bubbleGlobalMonitor {NSEvent.removeMonitor(bubbleGlobalMonitor)}
        bubbleLocalMonitor=nil;bubbleGlobalMonitor=nil
    }
    func handleTodoAction(_ action:String,id:String?) {
        guard taskRingOpen else {return}
        switch action {
        case "close":hidePetBubbles()
        case "select":if let task=todayTasks.first(where:{$0.id==id}) {showTaskDetails(task)}
        case "complete":if let id {completeTaskBubble(id)}
        case "back":detailGeneration+=1;todoSelection=nil;todoDetail=nil;todoError=nil;renderTaskRing()
        case "all":if let id=todoSelection {showTaskInAssistant(id:id)} else {showAssistant(page:"任务")}
        case "retry":if let selected=todayTasks.first(where:{$0.id==todoSelection}) {showTaskDetails(selected)} else {Task {await refreshTaskRing()}}
        case "review":if pet.reminderText != nil {openScheduleReminder()} else {showAssistant(page:"助手");webView.evaluateJavaScript("window.__campusPet?.showReview()")}
        default:break
        }
    }
    func refreshTaskRing() async {
        guard taskRingOpen,!loadingTaskRing,completingTasks.isEmpty else {return}
        guard ready,trusted(webView?.url) else {todoError="正在连接助手，请稍后刷新";renderTaskRing();return}
        loadingTaskRing=true;ringGeneration+=1;let generation=ringGeneration
        defer {if generation==ringGeneration {loadingTaskRing=false}}
        do {
            guard let data=try await js("""
                const get=async path=>{const r=await fetch('/api/'+path,{cache:'no-store'});if(!r.ok)throw new Error('今日待办读取失败');return r.json()};
                const [tasks,blocks,settings]=await Promise.all(['tasks','plan-blocks','settings'].map(get));return {tasks,blocks,timezone:settings.data.timezone};
                """) as? [String:Any],let tasks=data["tasks"] as? [[String:Any]],let blocks=data["blocks"] as? [[String:Any]] else {throw ServiceError.message("今日待办数据格式有误")}
            guard taskRingOpen,generation==ringGeneration else {return}
            taskTimezone=data["timezone"] as? String ?? "Asia/Shanghai"
            let completed=todayTasks.filter{completedTaskIDs.contains($0.id)}
            todayTasks=PetScheduledTask.today(tasks:tasks,blocks:blocks,timezone:taskTimezone)+completed
            todoError=nil
            if let id=todoSelection,!todayTasks.contains(where:{$0.id==id}) {detailGeneration+=1;todoDetail=nil;todoError="待办已删除或不再有今日安排，请返回列表刷新"}
            renderTaskRing()
        } catch {guard taskRingOpen,generation==ringGeneration else{return};todoError="读取失败："+TodoError.message(error);renderTaskRing()}
    }
    func renderTaskRing() {
        guard taskRingOpen else {return}
        let formatter=DateFormatter();formatter.timeZone=TimeZone(identifier:taskTimezone);formatter.dateFormat="HH:mm"
        let rows=todayTasks.map{task->[String:Any] in
            let date=(task.blocks.first?["starts_at"] as? String).flatMap(ScheduleReminder.parseDate)
            return ["id":task.id,"title":task.title,"time":date.map{formatter.string(from:$0)} ?? "待安排","pending":completingTasks.contains(task.id),"done":completedTaskIDs.contains(task.id)]
        }
        var state:[String:Any]=["status":"list","tasks":rows,"review":pet.reminderText != nil || latestAssistantMood == .approval]
        if let todoSelection {state["selected"]=todoSelection}
        if let todoDetail {state["detail"]=todoDetail}
        if let todoError {state["error"]=todoError}
        todoPanel?.render(PetTodoPanelState(payload:state))
    }
    func completeTaskBubble(_ id:String) {
        guard let task=todayTasks.first(where:{$0.id==id}),!completedTaskIDs.contains(id),!completingTasks.contains(id),ready,trusted(webView?.url) else{return}
        completingTasks.insert(id);ringGeneration+=1;loadingTaskRing=false;todoError=nil;renderTaskRing()
        let session=todoSession
        let savedKey=completionKeys[id]
        let key=savedKey?.revision == task.revision ? savedKey!.key : UUID().uuidString
        completionKeys[id]=(task.revision,key)
        Task {
            do {
                _=try await webView.callAsyncJavaScript("""
                    const token=(await(await fetch('/api/csrf')).json()).csrf_token;
                    const r=await fetch('/api/tasks/'+encodeURIComponent(id),{method:'PATCH',headers:{'Content-Type':'application/json','X-CSRF-Token':token,'Idempotency-Key':key},body:JSON.stringify({revision,status:'completed'})});
                    if(!r.ok){const body=await r.json().catch(()=>({}));throw new Error(typeof body.detail==='string'?body.detail:'任务完成未保存，请刷新重试')}
                    const saved=await r.json();window.dispatchEvent(new Event('campus-task-updated'));return saved;
                    """,arguments:["id":id,"revision":task.revision,"key":key],in:nil,contentWorld:.page)
                completingTasks.remove(id);completionKeys.removeValue(forKey:id)
                if taskRingOpen,session==todoSession {completedTaskIDs.insert(id);renderTaskRing()}
                else if taskRingOpen {await refreshTaskRing()}
                await refreshReminders()
            } catch {
                completingTasks.remove(id)
                if taskRingOpen,session==todoSession {
                    await refreshTaskRing()
                    guard taskRingOpen,session==todoSession else{return}
                    todoError="完成未保存："+TodoError.message(error)+"。请刷新或重试。";renderTaskRing()
                } else if taskRingOpen {await refreshTaskRing()}
            }
        }
    }
}
