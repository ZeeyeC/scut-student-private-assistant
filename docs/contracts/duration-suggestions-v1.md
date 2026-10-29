> Demo2.4.8规划/生成端已接入，扩展与兼容说明见 [甲方后续交付](../roadmap/demo2.4.8-a-followup.md)。原消费字段和领域存储继续兼容。

# T09 时长建议消费契约：duration-suggestions-v1

本增量只消费已存在的真实 typed `Resource(kind=duration_suggestion)`。A 的建议生成算法/生成服务尚未接入，没有生成端点、虚构建议或默认样本。GET 固定说明 generation_status=not_integrated；空列表展示“未接入生成服务 / 暂无可消费的有效时长建议”。本模块不调用模型。

## 集成

`app.duration_suggestions_routes.duration_suggestions_router(get_db, current_user)` 供主应用注册。get_db 须提供整个请求的原子串行事务（SQLite BEGIN IMMEDIATE）。前端 `DurationSuggestions` 无 props，使用既有 QueryClientProvider/api，查询 key 为 `['duration-suggestions']`。

- `GET /api/duration-suggestions`：只读、不创建 settings；返回 `{contract_version, generation_status, source_revision, invalid_suggestion_count, suggestions}`。未有资料时 source_revision=0。只读取本人资源，非 typed 建议不暴露其原始数据，计入 invalid_suggestion_count。
- `POST /api/duration-suggestions/{id}/actions`：需要 Idempotency-Key，body 为下例；action 为 accept/reject/restore_default。

```json
{
  "revision": 1,
  "task_revision": 2,
  "step_revision": 3,
  "source_revision": 8,
  "action": "accept"
}
```

所有版本是 >=1 的严格整数，不接受 bool/字符串。没有可由客户端任意修改建议分钟、样本、目标的字段。非本人建议404，失效或状态错误409，字段校验422。同 owner、suggestion、key、payload 精确重试先返回原 Receipt 结果，早于任何 freshness 计算；后续资料变化或重启不会重复修改步骤。相同键不同 payload409。

## 未来生成端写入的 typed data

本模块不提供这个写端点。未来 A 生成端按以下明确版本、原值与样本引用保存自己的 Resource，消费端仍独立校验：

```json
{
  "schema_version": 1,
  "source": "duration_generator",
  "task_id": "task-id",
  "task_revision": 2,
  "step_id": "step-id",
  "step_revision": 3,
  "source_revision": 8,
  "default_estimated_minutes": 30,
  "suggested_minutes": 45,
  "reasons": ["已确认执行样本比原预计更长"],
  "sample_basis": [
    {"execution_id": "record-id", "execution_revision": 1, "actual_minutes": 45, "feedback": "completed"}
  ],
  "state": "pending",
  "applied_step_revision": null,
  "applied_source_revision": null
}
```

suggested_minutes 为5–240严格整数，与现有步骤估时输入范围一致；default_estimated_minutes 为相同范围或 null（原来未知）。这里的“恢复默认”明确指恢复生成该建议前的原预计值，不假设系统统一时长。reasons 1–20条且不得空白。sample_basis 必须有1–1000条不重复的真实执行记录，actual_minutes 为0–100000整数，feedback 为 partial/completed/not_started/skipped。

本版目标为单个明确步骤，样本必须属于同一个本人任务/步骤，引用执行记录 revision，且 actual_minutes/feedback 与真实记录一致；已被更正替代的样本不能消费。本版没有跨任务相似度/聚类样本协议，生成算法如需此功能应另行升级契约，不能伪造同目标样本。

读取每项为 `{id,kind,revision,data,freshness,freshness_reason,current_task_revision,current_step_revision,current_source_revision,current_estimated_minutes,task_title,step_title}`。不可用的任务/步骤不泄露其他 owner 的标题。freshness=fresh 仅说明消费依据仍匹配，不代表建议模型的统计质量或置信度已验收。

## 动作与保护

pending 只可 accept/reject；accepted 只可 restore_default；rejected/restored 为本轮已处理终态。每次新动作检查：本人 task/step；step.data.task_id 等于目标；任务和步骤仍 open；建议版本、请求三版本与当前一致；生成时资料/任务/步骤版本一致；原默认等于当前步骤估时；样本真实、当前有效且未更正。

accept 仅更新目标 owned step 的 estimated_minutes 为 suggested_minutes，递增 step.revision 与全局 store.bump；任务版本、其他步骤、实际执行记录、spent_minutes、已有计划均不改。reject 只记录建议状态，不改估时、不 bump 排程版本。restore_default 必须在 accepted 后显式触发，校验接受后保存的 applied_step_revision/applied_source_revision 仍匹配当前，恢复原值（原值 null 则恢复未知），再次递增步骤/来源版本。中间手动修改或其他资料变化会阻止恢复，不覆盖新值。

建议 Resource、目标 step（需要时）、settings（需要时）、`planning_event(event_type=duration_suggestion_action)`、Receipt 全部在同一事务提交/回滚。事件包含 action、task_id、step_id、step_revision、source_revision。默认值、理由、样本和原生成版本保留在建议中供核对。没有正式排程写入；后续重排由原 A 草稿流程负责。

前端展示真实理由、逐条记录ID/版本/实际分钟/反馈、目标与资料版本、原默认/当前/建议分钟；只在 fresh 的合法状态出现明确接受、拒绝、恢复按钮。网络或5xx结果不明保留同一动作请求/幂等键；4xx显示真实错误，409刷新依据。没有乐观伪成功。

## 验证与边界

backend/tests/test_duration_suggestions.py 13项隔离 SQLite/API 测试通过：空态不写、真实 typed 理由样本、接受仅改目标、拒绝、恢复/未知原值、owner/归属、版本/资料/样本失效、样本更正、非法契约、精确重试/跨重启、手动编辑保护、完整回滚。前端 duration-suggestions-state 与 DurationSuggestions 两文件4项通过，覆盖冻结动作/版本、合法动作、失效阻断及空态/样本依据展示。

这完成乙方消费边界，不等于 T09 建议生成、样本量门槛/统计质量、模型学习效果或真实用户闭环验收完成。生成服务和真实建议仍待 A 提供；集成阶段负责主应用挂载与交互回归。
