# 甲 A3：每周重复禁排的最小闭环

本轮继续甲T04，目标是添加/修改/停用每周固定禁排、预览发生时间、在今日及7天排程中生效。只做硬禁排；软偏好评分、通勤候选及自动重排另行推进，不扩展乙的执行、档案或对话代码。

## 接口供乙复用

沿用 `POST /api/drafts/scheduling-constraint` 以及原草稿校对、确认、资源版本、planning_event和回执事务。`constraint`保留已有title、strength=hard、timezone、starts_at、ends_at；recurrence增加weekly，新增weekdays（1..7）及valid_until（可空）。单次规则不带星期/截止日期。starts_at在规则时区中的日期是生效起日，其钟点与ends_at的钟点/跨日偏移按所选星期重复；截止日包含当天开始的跨夜时段。空截止日期代表长期，不物化无限记录。

示例：`{title:"晚间固定安排", strength:"hard", recurrence:"weekly", timezone:"Asia/Shanghai", starts_at:"2026-10-28T19:00:00+08:00", ends_at:"2026-10-28T21:00:00+08:00", weekdays:[3,5], valid_until:"2026-12-31"}`。缺少明确钟点、星期或有效时区时程序拒绝，不猜“下午”等模糊信息。乙T13可补充同一草稿，不另建规则存储。

新增 `POST /api/drafts/{id}/constraint-preview?start=YYYY-MM-DD&end=YYYY-MM-DD`，请求为原DraftEdit的revision和payload；只读返回windows、affected_plans、active_after_save、时区与日期范围。预览最多一年；不写正式约束、不移动任务。修改已有约束仍绑定目标ID和版本，已停用规则修改后保持停用。

`expand_constraints(rows, lower, upper)`统一用于日历、排程、保留块检查和草稿预览。每周发生ID为`资源ID:当地日期`，constraint_id引用原规则；解释记录原规则revision。跨午夜尾段计入次日，按规则当地时间跨周/年展开，夏令时缺失或重复钟点报错，不猜时间。现有单次资源和ID保留。

排程规则版本改为weekly-constraints-1；升级前未确认旧计划需重新生成。新增/修改/停用规则沿用全局资料版本，旧方案不能确认；完成/锁定事实保留，新增规则不擅自移动已有安排。

本轮不修改乙负责的agent.py、tasks.py、Chat.tsx、TaskDetail.tsx或公共页面；界面只在甲的SchedulingConstraints.tsx实现，API统一生成。发布复用现有整包流程，保留Demo2.2和旧正式版本、个人资料与配置。已知S02对话刷新/SQLite取消连接问题仍归乙排查，未宣称修复。真实OCR准确率与学校特殊周亦不在本轮验收范围。

首轮整包浏览器27通过、1条既有分段课表用例因未等待计划生成完成而读取过早。已补充等待校对按钮后再断言API，业务断言保留。代码检查同时修正重复钟点锚点fold=1的验证，并补回归。首次日志和trace保存在工作区「资料归档/Demo2.4.3-首次验证失败-20261028」，最终结果看正式版本manifest。

第二次整包（307后端、14前端通过）在文字课表刷新处复现S02，出现CancelledError/no active connection后database is locked，浏览器24通过4失败。新增每周及原单次禁排4条通过。追加证据位于工作区「资料归档/Demo2.4.3-第二次验证-S02-20261028」，供乙复现定位；甲保持业务边界。
