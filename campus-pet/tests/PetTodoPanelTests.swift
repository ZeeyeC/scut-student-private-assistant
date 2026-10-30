import AppKit

@MainActor
func runPetTodoPanelTests() {
    for screen in [NSRect(x:0,y:0,width:1280,height:800),NSRect(x:-1280,y:200,width:1280,height:800),NSRect(x:0,y:0,width:640,height:480)] {
        for scale: CGFloat in [0.75,1,1.5] {
            let size=NSSize(width:109*scale,height:204*scale)
            for x in [screen.minX+12,screen.midX-size.width/2,screen.maxX-size.width-12] {
                for y in [screen.minY+12,screen.midY-size.height/2,screen.maxY-size.height-12] {
                    let character=NSRect(origin:NSPoint(x:x,y:y),size:size)
                    let frame=PetTodoLayout.frame(near:character,within:screen,preferredSide:.left)
                    precondition(screen.insetBy(dx:12,dy:12).contains(frame),"Todo panel must stay inside available screen")
                    precondition(!frame.intersects(character),"Todo panel must not cover visible character")
                    precondition(frame == PetTodoLayout.frame(near:character,within:screen,preferredSide:.left),"Placement must be stable")
                }
            }
        }
    }
    let frame=PetTodoLayout.frame(near:NSRect(x:700,y:100,width:109,height:204),within:NSRect(x:0,y:0,width:1280,height:800),preferredSide:.left)
    precondition(frame == NSRect(x:340,y:105,width:328,height:360),"Approved size and 32pt optical gap")
    let pet=PetView(frame:NSRect(x:0,y:0,width:190,height:240))
    for mood in [PetMood.starting,.idle,.thinking,.replying,.approval,.error,.sleeping] {
        pet.mood=mood;pet.reminderText="提醒";pet.taskRingText="旧条";
        precondition(!pet.isInteractive(NSPoint(x:15,y:200)),"Old transparent strip must never receive clicks")
        var clicks=0;var reminders=0;pet.onClick={clicks+=1};pet.onReminderClick={reminders+=1}
        precondition(pet.accessibilityPerformPress());precondition(clicks==1 && reminders==0,"AX press always toggles same todo panel")
    }
    for id in ["", "../task", "<script>", "x\n",String(repeating:"a",count:201)] {precondition(WorkspaceNavigation.taskTarget(id:id)==nil)}
    precondition(WorkspaceNavigation.taskTarget(id:"task-1") == ["page":"tasks","taskId":"task-1"])
    precondition(TodoError.message(NSError(domain:"WKErrorDomain",code:4,userInfo:["WKJavaScriptExceptionMessage":"Error: 待办已删除"]))=="Error: 待办已删除")
    print("PASS pet_todo_geometry_is_visible_without_covering_character / pet_has_no_top_strip_and_old_area_clicks_through")
}
