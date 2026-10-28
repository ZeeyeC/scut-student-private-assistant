# 执行事实 v1（乙方实现契约，待甲方复核）

基线：36c9bef93cd8fb961a955842f7d2b2db4dee44cc。Python模型位于`backend/app/execution_contracts.py`。B1仅实现手工补记和更正；计时、事件消费和自动重排尚未实现。

## 语义与读取

计划分钟保留在plan_block起止中；实际分钟来自用户记录；任务完成单独显式选择。缺记录actual_minutes=null，明确未执行为0。旧spent_minutes与按计划时长完成的记录只作为legacy_estimate，不升级为真实观察。

GET `/api/tasks/{id}/execution-summary?step_id=<可选>`返回：task_id、step_id、actual_minutes、legacy_estimated_minutes、unresolved_legacy_minutes、planning_spent_minutes、unknown_step_ids、effective_record_ids、source_revision。GET `/api/tasks/{id}/executions`返回所有事实和更正，使用既有Resource包络。

更正追加新execution资源，以supersedes_id指向旧记录；同execution_id仅链尾计入。旧记录不覆盖。各次独立执行累加；同一时间块只允许一个逻辑执行，后续变化走更正，避免不同入口各补记一次。

历史步骤总量先只读投影；首次明确修改才保存execution_baseline。旧完成块能在旧总量中完整覆盖时分配对应估算，其余为unallocated。新记录覆盖同一块的估算，不产生60+25=85。无法确定覆盖范围时，必须明确legacy_resolution=replace（替代未分配旧估算）或separate（确认为另一段投入）。步骤入口未指定单次安排但已有当前安排/旧估算时也必须核对，或显式绑定具体块。覆盖选择由服务端记录covered_plan_block_ids/separate_plan_block_ids；多块合计不能冒充单块精确分钟。旧总量保存不变时保留原分配；编辑导致来源不明的余额保持待核对，不能自动标为另一段投入。原估算和选择仍保留。甲可使用planning_spent_minutes兼容排程；actual_minutes用于真实投入统计，两者不可混同。

## 写入样例

所有写操作沿用CSRF、归属、BEGIN IMMEDIATE和Idempotency-Key。关联task/step/block版本必须匹配。以下ID为示意，实际请求使用查询到的资源。

POST `/api/executions`：

```json
{
  "client_operation_id": "operation-1",
  "execution_id": "execution-1",
  "task_id": "task-1", "task_revision": 1,
  "step_id": "step-1", "step_revision": 1,
  "plan_block_id": "block-1", "plan_block_revision": 1,
  "performed_on": "2026-10-28", "timezone": "Asia/Shanghai",
  "actual_minutes": 25, "feedback": "partial",
  "unfinished_reason": "insufficient_time", "task_status": "open"
}
```

结果：actual_minutes=25，task仍open，原计划起止仍60分钟；时间块标记已反馈，后续未完工作由甲计算，B1不自行移动日程。

POST `/api/executions/{当前有效记录id}/corrections`：

```json
{
  "client_operation_id": "operation-2", "revision": 1,
  "task_revision": 2, "actual_minutes": 20,
  "feedback": "partial", "unfinished_reason": "interrupted"
}
```

结果：原25保留，新20引用原记录，汇总为20。task_revision使用当前查询值，例中2仅作示意。feedback表示本次执行反馈，不自动完成整项任务。允许partial/completed/not_started/skipped；后两种分钟必须为0。原因可不填，不要求私人事由。

## 重放、失败和事件

| 输入/条件 | 结果 |
| --- | --- |
| 无记录 | actual=null；有旧记录时单列估算 |
| 用户记录0 | actual=0，有事实记录及来源 |
| 同键同内容重试 | 原回执，单个事实及事件 |
| 新请求键重复同逻辑执行/同操作 | 原结果或409，不重复累计 |
| 同键不同内容；已有更正的旧记录再更正 | 409，要求读取当前状态 |
| 负分钟、浮点分钟、非法时区、关联不完整 | 422 |
| 其他用户或不存在的关联 | 404 |
| 关联版本过期/来源覆盖不明确 | 409，不写半份事实 |
| 写事实后事件保存失败 | 整体回滚：事实、投影、版本和回执均不落库 |
| 旧计划生成后新增/更正执行 | source_revision变化，旧计划确认409，正式时间不自动移动 |

execution_changed沿用planning_event：schema_version、source_id、source_revision、dedupe_key、status=recorded、details。details提供task/step/block、有效记录及数据版本；不直接进入“已重排”。事件、正式事实、投影及回执同事务提交。

旧`PATCH /steps/{id}`的spent_minutes保留“总量覆盖”语义，并作为可追溯估算调整；不能削减已记录实际值，精确事实需通过更正修改。旧时间块完成只产生估算，若该块已有实际值则不再累加。桌宠任务完成不调用分钟补记。

## 公共接入与待交接

甲复核main.py注册、planner.py旧完成入口、deletion.py删除及生成API类型。删除任务明确级联其执行/基线；已有执行事实的未完成步骤暂拒绝重新拆解，避免删除事实关联。导出和停服备份沿用现有完整Resource和数据库机制，不新增私有文件。

未冻结的远期范围：B2开始/暂停计时及异常恢复的版本规则，甲T11事件消费，T07/T08领域契约。甲乙真实联调/复核尚未完成；本地实现验证不得替代其验收。
