# 用户确认目标契约 goals-v1

本增量提供 B5/T08 独立的长期目标保存、编辑、暂停/恢复、子任务与现有任务关联。它不提供 A T04/T06/T11 的容量计算、未来安排或自动调整，也不自动生成任务、计划或时间块。

## HTTP 与事务

`goal_router(get_db, current_user)` 由主应用注册。`get_db` 必须提供单次请求内原子提交/回滚和串行写入（SQLite 使用 `BEGIN IMMEDIATE`）。身份取自 `current_user`，客户端不传 owner。

- `GET /api/goals`：只读，不创建 settings。返回 `{contract_version, source_revision, capacity, goals}`；未创建目标时 `goals: []`。
- `POST /api/goals`：确认新目标。`revision` 为整数 `0`（省略也为 0）。成功返回 GoalView，目标首版本为 1。
- `PATCH /api/goals/{id}`：请求包含整数 `revision >= 1` 和至少一个修改字段。字段省略表示保留；仅 `deadline: null` 可明确恢复未知。`subtasks` 若提供则替换当前子任务列表；`[]` 明确移除全部当前子任务。

POST/PATCH 必须有 `Idempotency-Key`（1–160 字符）；相同 owner、scope、key、payload 重试返回同一结果，不重复追加事件或完成事实。相同键不同请求体返回 409；版本过期返回 409；非本人或种类错误资源返回 404；输入无效返回 422。新目标和每次修改在同一事务中写入 `Resource(kind=goal)`、全局 `store.bump`、`Resource(kind=planning_event, event_type=goal_changed)` 与 Receipt。失败全部回滚。幂等结果是写入当时的响应快照；重新 GET 获取最新引用与全局来源版本。

## 写入字段

```json
{
  "revision": 0,
  "title": "英语阅读",
  "description": "每周读一章",
  "deadline": null,
  "weekly_budget_minutes": 60,
  "priority": 2,
  "load_category": "study",
  "allowed_adjustment": "ask",
  "paused": false,
  "subtasks": [
    {"title": "第一章", "status": "open", "estimated_minutes": 20, "task_id": null}
  ]
}
```

`title` 去首尾空白后不能为空，最大 200 字符；description 最大 4000。deadline 为带显式 UTC 偏移/Z 的时间，未知可 null。weekly_budget_minutes 是 0–10080 的严格整数，0 是用户明确不投入，不代表可用容量为零。priority 是 1–3 严格整数，3 为高、1 为低，与现有任务优先级一致；load_category 为 study/exercise/other；allowed_adjustment 为 reduce/delay/ask，仅记录用户许可，不执行调整；paused 为严格布尔。

子任务最多 200 条，title 最大 200 字符，status 为 open/completed，estimated_minutes 是 0–100000 的严格整数。task_id 可为 null 或本人现有 `task` Resource ID。创建目标/子任务时不传 id；系统生成稳定 UUID。PATCH 中保留已存在子任务 id；省略 id 表示新子任务；重复或不属于当前目标的 id 拒绝。仅建立引用，不修改被关联任务，任务的 completed 状态也不会自动改变子任务状态。

## GoalView 读取字段

```json
{
  "id": "goal-uuid",
  "kind": "goal",
  "revision": 1,
  "source_revision": 2,
  "contract_version": "goals-v1",
  "capacity": {
    "status": "unknown",
    "weekly_available_minutes": null,
    "integration_status": "pending"
  },
  "arrangements": [],
  "references": [
    {"subtask_id": "subtask-uuid", "task_id": "task-uuid", "available": true,
     "revision": 1, "title": "现有任务", "status": "open"}
  ],
  "data": {
    "schema_version": 1,
    "source": "user",
    "confirmed": true,
    "updated_at": "2026-10-28T01:00:00Z",
    "title": "英语阅读",
    "description": "每周读一章",
    "deadline": null,
    "weekly_budget_minutes": 60,
    "priority": 2,
    "load_category": "study",
    "allowed_adjustment": "ask",
    "paused": false,
    "subtasks": [
      {"id": "subtask-uuid", "title": "第一章", "status": "open", "estimated_minutes": 20, "task_id": "task-uuid"}
    ],
    "completion_history": []
  }
}
```

revision 是目标版本；source_revision 是当前用户的全局来源版本。来源、已确认标记与契约版本由服务端维护，客户端不得写入。GET 顶层和每个目标的 capacity 均为 unknown/null/pending；不能将用户预算或旧日程规则宣称为 A 的容量结果。

每次子任务从 open 变 completed（或创建为 completed）追加不可被 PATCH 覆盖的完成事实：`{subtask_id, title, estimated_minutes, task_id, completed_at, goal_revision}`。重复保存相同 completed 状态不追加；重新打开后再次完成会记录第二次完成。编辑名称、移除子任务、暂停/恢复目标都保留已有 completion_history，历史快照不会跟随当前字段改变。

references 逐条展示当前 task 的可用状态。任务删除后保留 task_id，返回 available=false 且 revision/title/status=null；目标仍可编辑或暂停。改变/新建关联必须重新校验任务归属。暂停仅改变 paused，不删除子任务、任务、完成事实或已有计划。当前 arrangements 始终为空，包括暂停目标。

## 前端与验收范围

`Goals` 为无需 props 的独立组件，使用既有 QueryClientProvider 与 api；查询 key 为 goals 和 tasks。支持新建、读取、编辑、暂停/恢复、子任务增删/状态/时长、任务关联。提交前明确确认；失败显示真实错误，网络/服务端结果未确认时保留同一 payload 和幂等键重试；409 刷新最新目标，避免覆盖。

本轮 API 固定为 GET/POST/PATCH，没有目标删除接口；暂停保留资料。容量、目标对比可用时间、目标安排、自动调整仍待 A 接入及真实样本对照验收，不能把目标存储测试通过视为任务书全部完成。没有模型调用或付费测试。

隔离 SQLite/API 覆盖：身份和 owner、创建/读取/编辑、稳定子任务、任务关联、零预算、带时区/未知截止、未知容量、暂停保留完成事实、恢复、幂等/版本、跨重启读取、事件失败全事务回滚、已删除引用继续暂停。前端验证输入序列化、稳定标识、零与未知区别、幂等重试快照，以及真实组件 SSR 中的暂停/容量/完成事实展示。主应用注册挂载和全量回归由集成阶段完成。
