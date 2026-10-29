# 多轮规划协商 v1

本模块实现 B7/T15 的可恢复规划意图、真实候选比较与选择草稿。候选由甲方 `planning_result`、`compare_plans`、`build_plan`、`risk_report` 和 `replan_report` 计算；不实现第二套分配算法，不推断晚间、睡眠或个人习惯。正式日程只由既有 `imports.commit_draft` → `planner.save_plan` 确认流程修改。

## 路由与服务

注册 `negotiation_router(get_db, current_user)`。以下路径以 `/api/planning-intents` 为前缀；写入要求原鉴权、CSRF 与 `Idempotency-Key`。

| 方法与路径 | 请求模型 | 公开服务函数 | 响应 |
| --- | --- | --- | --- |
| GET 空路径 | 无 | `read_intents(db, owner)` | `ResourceView[]` |
| POST 空路径 | `IntentCreate` | `create_intent(db, owner, body)` | `ResourceView` |
| PATCH `/{rid}` | `IntentPatch` | `patch_intent(db, owner, rid, body)` | `ResourceView` |
| POST `/{rid}/preview` | `IntentAction` | `preview_intent(db, owner, rid, body)` | `ResourceView` |
| POST `/{rid}/choose` | `IntentChoose` | `choose_intent(db, owner, rid, body)` | `{intent: ResourceView, draft: ResourceView}` |
| POST `/{rid}/cancel` | `IntentAction` | `cancel_intent(db, owner, rid, body)` | `ResourceView` |

模型位于 `backend/app/negotiation_contracts.py`，服务位于 `backend/app/negotiation.py`。服务使用调用方事务，不自行提交。路由在调用服务**之前**使用 `store.mutate` 检查回执；其他调用方也必须采用相同做法。模型工具只允许创建、读取、更新、预览，不开放 choose、cancel 或正式确认能力；选择来自真实 UI，确认使用原计划草稿入口。

`IntentCreate = {source_revision, data: IntentData}`；`IntentPatch` 在此基础上增加 `revision`，用完整的明确条件替换同一 ID，保存上一轮条件到 `turns`。调用方修改一项时应先读取当前条件并合并，不能将省略字段误当作用户要求清除。`IntentAction = {revision, source_revision}`；`IntentChoose` 再增加 `option_id: earliest | preferred`。

`source_revision` 为当前设置资源的全局资料版本。意图元数据操作不会自行提升该版本。请求中的意图版本与资料版本都必须当前有效；重新预览允许对当前资料版本重算原意图。选择还要求所存预览的资料版本一致；仅修改请求中的版本数字不能使旧预览有效。

## 明确条件

```json
{
  "description": "周一保住复习，尽量晚一点开始",
  "target_date": "2030-12-30",
  "horizon_days": 1,
  "timezone": "Asia/Shanghai",
  "protected_intervals": [],
  "preferred_intervals": [
    {"starts_at": "2030-12-30T11:00:00+08:00", "ends_at": "2030-12-30T12:00:00+08:00"}
  ],
  "reduced_daily_limit_minutes": null,
  "keep_block_ids": []
}
```

日期、1–7 天范围和 IANA 时区必须明确，日期不能早于该时区今天，时区需匹配当前设置。描述用于保存用户的目标与取舍，**描述里的自然语言不会自动转换为条件**。半开时段必须带明确时区偏移、结束晚于开始，并位于本轮范围内；它们通过甲方 `SchedulingConstraint` 校验。

保护时段作为临时 hard 条件；偏好时段作为临时 soft 条件。二者仅加入读取输入的深拷贝，在候选快照中标记 `source=temporary_intent`。为复用甲算法，快照条目的 active/confirmed 为 true，但不会写成正式 `scheduling_constraint` 资源。选择、取消或确认计划均不把这些条目升级为个人习惯或永久约束。

临时每日上限为空时沿用已确认设置；明确填写只允许降低上限，不允许放宽。不会修改正式设置。保留 ID 必须属于当前用户、真实存在且在本轮日期范围；跨用户或不存在返回 404，范围外返回 422。

## 持久状态与比较

`planning_intent` 使用原 Resource 包络。`data` 包含：

- `schema_version=1`、`status=active|chosen|cancelled`、`source_revision`；
- `conditions`：当前明确条件；`turns`：修改前的条件及意图版本；
- `preview`：资料版本、候选列表、冲突理由及解释；
- `choice`：已选 `option_id` 和 `draft_id`，未选为空。

GET 不调用模型或重新计算，重启后仍能恢复同一意图。修改清除旧预览；已选择但尚未确认的本意图草稿会失效。已确认日程保持原样。

两个策略只有在实际时间分配不同才分别展示；按任务、步骤、起止时间去重，不能靠标题或生成 ID 伪造备选。每个候选包含新增分钟、未排分钟、偏好内分钟、保留数量、风险原因、真实新增/移除/保留项，以及甲算法的实际 payload/source 快照。存在部分可排工作时可展示剩余负荷与截止风险，不承诺全部完成。无新增可排工作且仍有未安排/未知工作时，不拿范围外历史安排冒充可行方案。只有一种结果或无解时明确说明并请求修改条件。

既有硬条件完整保留。锁定、完成、范围外安排及未结束计时关联安排受到保护；用户明确保留的块也加入甲方的保留输入。若甲方结果丢失保留项或报告冲突警告，本模块不将其宣传为可行候选。候选使用甲方选择性修复报告，使确认流程只移除其真实计算的 removed IDs，避免重新删除本轮保留的未锁定块。

## 选择、幂等与取消

选择不重新运行算法；使用当前预览保存的实际 payload、generated_hash、rule_version 与 planning_inputs 调用 `imports.create_draft(..., "plan", ...)`。选择前正式 `plan_block` 和约束均不修改。候选新增或待移除安排已经开始时拒绝选择，要求重算。

原计划确认继续检查资料版本、规则版本、生成 hash、任务步骤归属、计时保护和当前时间边界；不存在绕过确认的新入口。

同一请求键、同一内容的重试优先返回原历史回执，即使之后资料变化、草稿确认或意图取消，也不重算、不新增草稿。新请求键仍须通过当前版本和状态检查。幂等键用于不同内容返回 409。意图、草稿和回执在同一事务内；失败整体回滚。

取消只将意图标记 cancelled，并使其尚未确认的候选草稿失效；不删除正式日程、已确认草稿或先前确认的硬约束。取消后可修改同一意图继续讨论。若资料已变化，取消请求需携带当前资料版本。

## 界面与验证边界

`NegotiationPanel` 为命名导出，接受可选 `onDraft?: (draft: Resource) => void`。默认直接嵌入原 `PlanReview`；父界面无需创建新确认协议。界面提供日期、目标、临时保护/偏好、降负荷与保留项；时段使用 `datetime-local` 控件，复用 `constraintInput`/`constraintInstant` 按设置 IANA 时区显示和转换，无需填写 API 时间串。夏令时跳过或重复钟点会要求另选明确时间，不擅自消歧。保存修改后才能重新预览和选择。已选 ID 与未确认响应的操作键/完整请求按当前用户保存在 sessionStorage，可在刷新后重试；浏览器不允许存储时，当前组件仍保留内存重试状态。

隔离测试 `backend/tests/test_negotiation.py` 使用真实 SQLite、甲规划函数和原 `commit_draft`，覆盖双方案、同案、无解、已确认硬条件、跨年范围、keep/locked/未结束计时、版本/归属/非法时段、取消重启、选择回执历史重放和事务失败。前端 `negotiation-state.test.ts` 覆盖不猜日期时段、操作内容冻结与当前用户的选择恢复。

本模块测试不等于整应用浏览器、原生 App、真实模型或真实个人资料验收。公共注册、模型工具权限、实际页面挂载及全量回归由本轮主代理统一集成；甲方个性化/目标算法未交付的能力不会在此伪造。
