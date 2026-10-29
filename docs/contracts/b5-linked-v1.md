# B5 目标共享容量与复盘计划草稿联动

本契约消费甲的 `planner.planning_result` / `planner.generate_plan` 与原草稿确认流程，不新增排程、目标排序、耗时估计或文字优化算法。旧 `GoalData`、`GoalCapacity`、`GoalView` 和 `/api/goals` 的结构保持兼容；旧 `capacity.status=unknown` 仅代表尚未交付的逐目标分配，新共享容量是独立接口。

## 共享目标容量

集成：`goal_capacity_router(get_db, current_user)`；领域函数 `read_goal_capacity(db, owner, week_start=None, report_timezone=None, expected_source_revision=None)`。

`GET /api/goal-capacity?week_start=2026-11-02&timezone=Asia%2FShanghai&expected_source_revision=4`

- `week_start` 可省略，按已保存排程时区选择下一个周一；显式范围必须是尚未开始的周一到下周一，严格覆盖 7 个本地日期。`week_end` 不含截止日；时区来自排程设置。传入不同时区或已开始/非周一范围返回 422。
- 可选 `expected_source_revision` 与当前设置版本不符返回 409。每次读取重新消费甲服务，无本地缓存计算或日程写入。
- `contract_version: goal-capacity-v1`；`status: known | unknown`；`week_start/week_end/timezone/source_revision` 说明计算范围与来源。
- `shared_capacity_upper_bound_minutes` 是甲 `capacity.capacity_upper_bound_minutes`，仅有一份共享上限。`active_weekly_budget_minutes` 为全部未暂停目标预算合计；`minimum_deficit_minutes=max(0, 活动预算合计-共享上限)`。上限不代表保证可安排工作量，更不等于逐目标分配。
- `active_goal_ids/paused_goal_ids/goal_revisions` 保留目标身份及版本；暂停目标不计预算，读取不更改其任务或完成历史。已有独立任务仍由甲按任务状态排程，不能把排除目标预算描述为已经实现目标暂停排程算法。
- `capacity` 原样返回甲真实容量报告，包括时间窗、未知耗时数量与警告。没有排程设置时返回 `status=unknown`，上限、缺口和 `capacity` 为 null，不在只读接口写入默认设置。
- `actual_minutes` 保持 null，不能将历史预计分钟、已安排分钟或容量上限推断成实际投入/剩余目标预算。
- 登录及 owner 隔离由注入依赖和领域查询共同执行，不读取其他用户目标。

已验证真实甲输入：未来周每日 60 分钟，周一被固定事项占满，其余六天共 **360 分钟**；两个活动目标各预算 300 分钟，活动合计 **600 分钟**、至少缺口 **240 分钟**。另一个暂停目标的 500 分钟不计入，完成历史仍保留。

## 复盘生成原计划草稿

集成：现有 `review_router(get_db, current_user)` 自动增加 `POST /api/weekly-review/plan-draft`。请求必须带 `Idempotency-Key`，正文：

```json
{"week_start":"2026-10-26","timezone":"Asia/Shanghai","revision":1,"source_revision":4}
```

`revision` 是最新周复盘资源版本，`source_revision` 是最新报告的当前设置版本。必须先通过现有 `/weekly-review/actions` 接受有内容的意向；旧持久状态 `accepted_pending_integration` 为兼容保留，界面显示“已接受调整意向，可生成下周计划草稿”。

1. `create_next_week_draft(db, owner, body)` 检查 owner、复盘版本、当前来源版本、已接受状态，以及复盘时区与排程设置一致。
2. 目标周严格为 `review.week_start + 7天`，跨年同样成立；该周已开始返回 422，不能把历史复盘自动转换成另一个未来周。
3. 调用甲 `generate_plan(target=目标周周一,horizon=7)`；保留甲 `source_revision/planning_inputs/generated_hash/rule_version`。文字意向仅附在 `source.weekly_review_reason` 作为来源，甲尚无任意文字优化接口；时间偏好/禁排等仍需用户先通过相应入口确认。
4. 返回 `{review, draft, next_week_plan}`。`draft` 是原 `ResourceView`，可以直接交现有 `Today.PlanReview` 校对。生成前后不写 `plan_block/plan_snapshot`。
5. 同一个幂等请求丢响应后重放返回原结果；新键且同一意向、同一版本的有效 pending 关联复用同一草稿。甲的全局计划草稿替代规则仍生效，新计划可能使旧 pending 草稿变成 superseded。
6. 链接更新复盘版本并记录 `weekly_review_plan_linked` 事件，但不 bump 设置版本，否则刚生成的草稿会立即过期。原确认入口继续执行来源版本、生成 hash、排程规则与时间检查；只有明确确认才保存正式安排和快照。
7. 已确认的同一意向不能重复生成；再次明确接受新的意向后，可另建草稿，保留旧确认快照与正式安排直到原流程再次确认。

复盘资源增加：`accepted_intent_revision` 标识最近一次明确接受；`data.plan_links[]` 追加 `draft_id/week_start/timezone/source_revision/accepted_review_revision/intent_revision/generated_at`。现有 `history` 保留选择记录。`restore/reject/reason` 保留 `plan_links`，不会撤销或删除已确认的日程、快照、执行事实。

## 可恢复的真实状态

`GET /api/weekly-review` 增加 `next_week_plan`；由 `linked_plan_view(...)` 只读派生：

- 通用字段：`week_start/week_end/timezone/status/draft_id/draft/snapshot_ids/reason/is_current_intent`。关联存在时附 `generated_source_revision`。
- `not_created`：没有草稿关联。
- `pending`：原草稿仍 pending、来源版本一致、规则与 hash 未变、目标周尚未开始；仅此状态返回 `draft` 给原 PlanReview。
- `confirmed`：真实 `plan_snapshot.data.draft_id` 证明已经确认，返回相应 `snapshot_ids`；后续资料变化、恢复意向不会抹除确认事实。
- `invalidated`：草稿删除/替代/改变、资料或规则变化、目标周已开始。`reason` 分别为 `draft_unavailable/draft_superseded/draft_changed/source_changed/rule_changed/planning_week_started` 等；不再提供可确认的草稿。
- `is_current_intent` 区分旧确认记录与新接受的意向；恢复待选择后仍能查看历史真实确认记录。

顶层 `next_week_optimization=draft_review_available` 表示已有真实计划草稿校对入口，不表示自由文字已被优化执行。原始周/调整后周投影和实际执行事实的计算保持原样。

前端 `Goals` 使用新接口一次展示共享上限、活动总预算、至少缺口和明确范围；`WeeklyReview` 显式触发草稿、保留同一幂等键重试、使用原 PlanReview 并在动作后失效查询。原 `DraftActions` 确认后已有全局查询失效，周复盘会重新读取真实确认状态。

## 验证与未达成边界

隔离 SQLite 与真实 FastAPI/甲函数验证：共享 360/600/240、暂停/完成保留、未知、来源版本、owner；原始 60 分钟快照与真实 25 分钟执行保存不变；真实下周草稿/确认快照、重启、同键重放/不同键复用、失效/重建、恢复不删日程、跨年、历史目标周拒绝、生成失败整体回滚。React 组件与状态测试覆盖共享容量、未知/0、原 PlanReview、确认快照及失效状态。日志位于 `.superpowers/sdd/2026-10-29-b-interaction/b5-*.log`。

尚未交付的甲职责仍包括逐目标分配/排序、任意文字意向优化和 T09 真实耗时建议生成；本接口未伪造这些结果。真实外部用户样本、付费模型联调、打包、全量回归与浏览器集成由父任务统一验收，本模块测试通过不等于任务书全部完成。
