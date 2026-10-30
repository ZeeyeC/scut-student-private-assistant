import AppKit
import WebKit

extension AppDelegate {
    @objc func openTodos() {showAssistant(page:"任务")}
    func showTaskInAssistant(id:String) {
        guard WorkspaceNavigation.taskTarget(id:id) != nil else{return}
        hidePetBubbles();requestedPage="任务";requestedTaskID=id
        NSApp.activate(ignoringOtherApps:true);assistant.makeKeyAndOrderFront(nil);navigate()
    }
    func showTaskDetails(_ selected:PetScheduledTask) {
        guard taskRingOpen else{return}
        detailGeneration+=1;let request=detailGeneration;let session=todoSession
        todoSelection=selected.id;todoDetail=nil;todoError=nil;renderTaskRing()
        Task {
            do {
                guard ready,trusted(webView?.url) else {throw ServiceError.message("请先连接本机助手")}
                let response=try await webView.callAsyncJavaScript("""
                    const get=async path=>{const r=await fetch('/api/'+path,{cache:'no-store'});if(!r.ok)throw new Error(r.status===404?'待办已删除，请返回列表刷新':'待办详情暂时无法读取');return r.json()};
                    const [task,steps,blocks,settings,courses]=await Promise.all(['tasks/'+encodeURIComponent(id),'tasks/'+encodeURIComponent(id)+'/steps','plan-blocks','settings','courses'].map(get));
                    return {task,steps,blocks,courses,timezone:settings.data.timezone};
                    """,arguments:["id":selected.id],in:nil,contentWorld:.page)
                guard taskRingOpen,session==todoSession,request==detailGeneration,todoSelection==selected.id else{return}
                guard let response=response as? [String:Any],let task=response["task"] as? [String:Any],let data=task["data"] as? [String:Any] else {throw ServiceError.message("待办详情数据格式有误")}
                let tz=response["timezone"] as? String ?? "Asia/Shanghai"
                let date=DateFormatter();date.locale=Locale(identifier:"zh_CN");date.timeZone=TimeZone(identifier:tz);date.dateFormat="MM月dd日 HH:mm"
                func dateText(_ value:Any?)->String {guard let text=value as? String,let instant=ScheduleReminder.parseDate(text) else{return "待确认"};return date.string(from:instant)}
                let courses=response["courses"] as? [[String:Any]] ?? []
                let course=courses.first{$0["id"] as? String == data["course_id"] as? String}?["data"] as? [String:Any]
                let steps=(response["steps"] as? [[String:Any]] ?? []).compactMap{$0["data"] as? [String:Any]}
                let estimates=steps.compactMap{$0["estimated_minutes"] as? Int}
                let estimate=steps.isEmpty || estimates.count != steps.count ? "待估时" : "\(estimates.reduce(0,+)) 分钟"
                let scheduled=PetScheduledTask.today(tasks:[task],blocks:response["blocks"] as? [[String:Any]] ?? [],timezone:tz).first
                let times=(scheduled?.blocks ?? []).map{dateText($0["starts_at"])+"—"+dateText($0["ends_at"])}.joined(separator:"\n")
                todoDetail=["title":data["title"] as? String ?? selected.title,"course":course?["name"] as? String ?? "未分类","time":times.isEmpty ? "待安排" : times,"estimate":estimate,"due":dateText(data["due_at"]),"requirements":(data["requirements"] as? [String] ?? []).joined(separator:"\n"),"steps":steps.map{(($0["status"] as? String == "completed") ? "✓ " : "○ ")+($0["title"] as? String ?? "学习步骤")}]
                renderTaskRing()
            } catch {guard taskRingOpen,session==todoSession,request==detailGeneration,todoSelection==selected.id else{return};todoError=TodoError.message(error);renderTaskRing()}
        }
    }
}
