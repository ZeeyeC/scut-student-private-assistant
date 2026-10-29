# B6 主动建议消费与生命周期：proactive-v1

当前实现是应用内无声建议，默认关闭。它消费 A 的 planning_result、risk_report、replan_report，不自行计算容量、排程或用户习惯；应用没有外部观察、OS 通知或后台唤醒服务。前端只有在页面可见且获得焦点、并明确开启建议时，挂载后与每 60 秒刷新；失焦暂停刷新与展示。

## 集成与接口

注册 `app.proactive_routes.proactive_router(get_db, current_user)`。get_db 必须为每次写请求提供串行原子事务，SQLite 使用 BEGIN IMMEDIATE。

- `GET /api/proactive/preferences`：只读，未保存时 revision=0，enabled=false，timezone=null，quiet_hours=null。
- `PUT /api/proactive/preferences`：`{revision, data}`，需要 Idempotency-Key。data 为 enabled、全部五种 categories 的严格布尔开关、timezone（有效 IANA 或 null）、quiet_hours（null 未知、[] 明确不设、数组明确设置）。
- `GET /api/proactive/suggestions`：读取已保存建议并按当前设置和时刻计算 visible，不调用 A 计算。返回 contract_version、preferences、suggestions、suppression、source_revision、capacity；后两项只有 refresh 结果有当前 A 计算。
- `POST /api/proactive/refresh`：`{app_active: true/false}`。关闭/未活跃时不调用 A；按当前事实进行确定性 reconciliation，不使用 Receipt 缓存刷新结果。
- `POST /api/proactive/suggestions/{id}/actions`：`{revision, fingerprint, action, snooze_minutes?, accept_mode?}`，需要 Idempotency-Key。action 为 snooze（1–10080 整数分钟）、dismiss、disable_category、accept（必须指定 details/replan）。

categories 为 deadline/capacity/unknown_estimate/available_window/facts_changed，必须全部出现且使用布尔。quiet_hours 每条为 `{weekdays:[1..7], start:"HH:MM", end:"HH:MM"}`；星期严格整数不重复；跨午夜按开始日归属，区间含开始不含结束。星期日22:00–02:00覆盖星期一凌晨，DST 重复小时按真实 instant 转本地时间后两次均判断安静。启用安静时段必须明确时区，不推断睡眠习惯。

## 建议与依据

Resource kind 为 proactive_suggestion，外层 id/kind/revision；data 含：

- schema_version=1，category，issue_key，同问题依据的 fingerprint。
- title、reasons、gaps、rank；source_revision、sources（id/kind/revision）、evidence、task_id。
- state、first_seen_at、snoozed_until、resolved_at；visible 是读取时计算值。

类别来源：deadline 消费 A 的截止/未排风险；即使 A 可排入全部工作，已确认且未来48小时内的待完成截止也会显示提醒（evidence.trigger=confirmed_deadline_within_48h），不假设准备或通勤耗时。capacity 使用 A 的未排工作量，unknown_estimate 保留未知，不按0。available_window 必须是 A 真实空档中至少20分钟且 A 已校验能放入的待完成任务步骤，仅有空白时段不提示可学习。facts_changed 展示 A 对原安排移除或需校对的依据；不改写原安排。

按 rank、确认截止、依赖缺口、未排工作量等稳定排序。一般次序为逾期、原安排事实变化、截止风险、容量、耗时缺口、学习空档。实际执行样本缺失时明确保持未知，A 当前 spent 计算不被宣称为权威执行汇总。

## 持久状态与动作

状态为 pending/snoozed/dismissed/accepted/resolved/superseded。同 issue_key 与 fingerprint 不重复新增；无关全局版本和时钟推进不应让相同原因重新提醒。依据改变时旧条 superseded，新建 pending；问题消失 resolved；之后复现创建新一轮记录。snoozed 到期在刷新后恢复 pending。dismiss/accept 会保留处理状态跨重启。

每次新 action 前重新调用 A 核对依据、设置、建议 revision/fingerprint；过期返回409。已提交同一 Receipt 的精确重试先返回历史动作结果，不因后续资料变化再次执行。相同键不同参数409；非本人404；请求校验错误422。设置/建议/事件/Receipt 在请求事务内共同回滚；通知偏好不 bump 排程资料版本。

accept/details 仅返回已校验本人 open_task_id，不完成任务。前端传 onOpenTask 时交由宿主真正打开对应详情；默认回到“作业”并展示关联任务ID，因此宿主应接好详情回调后才能宣称已完成具体任务详情导航验收。accept/replan 调用 A 原 replan_draft，返回 draft + requires_confirmation=true，不创建正式 plan_block；随后必须走原草稿核对确认入口，确认时仍校验最新事实。

前端导出 ProactiveSettings、ProactiveSuggestions，后者支持可选 onOpenTask/onOpenDraft；无回调时可内嵌 PlanReview。网络结果不明保留原 payload/key 重试，409刷新，所有失败显示实际错误。

## 本轮实际验证与未完成范围

backend/tests/test_proactive.py：16项真实隔离 SQLite + A planner 测试通过，覆盖启用/活跃门槛、真实20分钟空档、风险/容量、排序、去重/跨重启、稍后/安静/DST、类别关闭、变化/消失/再现、明确截止提醒、严格嵌套类型、owner、幂等/过期、草稿与事务回滚。前端 proactive-state/ProactiveSuggestions 两文件11项通过。

上述是模块自动验证；主应用挂载、真正详情导航、应用前后台交互及真实用户样本验收由集成阶段完成。缺少真实准备时间、权威执行反馈与生活约束时不补造事实，也不宣称 B6 端到端任务书全部完成。
