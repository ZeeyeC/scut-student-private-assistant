# 对话约束与批准校对

`conversation_constraint_router(get_db,current_user)` 注册 `/api/constraint-intents`，使用现有 Resource、Receipt 和串行请求事务。领域函数由 HTTP 与真实 Agent 工具共同调用，不复制甲的约束展开、冲突或排程算法。

- GET 列表、GET `/{id}`：返回本人候选、原草稿和实际已确认规则。可按本人 thread_id 查询，跨用户 404。
- POST：`{data:{day_expression,start_time,end_time,end_day_offset,recurrence,weekdays,valid_until,strength,timezone},thread_id?}`。日期、钟点可以未知。创建仅保存候选。
- PATCH `/{id}`：`{revision,changes}`。补充原 ID；原草稿已准备时，完整修改更新同一草稿并递增版本；清空必要信息会取消旧草稿，防止仍保存旧时间。
- POST `/{id}/prepare`：`{revision}`。信息完整才调用甲原 scheduling_constraint 草稿，重复准备返回同一份；确认仍经原 ConstraintReview。
- POST `/{id}/cancel`：未确认时取消候选和待确认草稿；已确认时只标记停用请求。用户仍需在页面明确调用甲的版本化规则停用接口。历史日程不被删除。

写接口均带 Idempotency-Key；精确重试返回历史结果，相同键不同参数 409。候选修改不增加正式排程来源版本。规则确认和停用沿用甲的版本与事件机制。

相对日期按服务器收到该消息的日期和明确时区定位；保存标准年月日，刷新不会自动滚到下周。跨年、下下周、明确每周、次日结束和夏令时均保留实际含义。“下午”“晚上”不推断钟点；开始/结束缺失会追问。正式标题默认“不可安排”，不提供私人原因字段，也不保存日期文字中附带的医院等事由。原聊天消息仍属于用户的聊天历史。

Agent 新工具允许查询、创建、补充、准备及取消约束候选；规划工具允许读取甲真实容量/风险/方案、继续原 planning_intent 并预览。模型没有协商选择或自行批准工具。任何正式修改依旧由用户在页面确认。

Agent 的 commit_import 人工批准增加 `conflict_tokens:{draft_id:token}` 和 `conflict_acknowledged:[draft_id]`。适用甲 REVIEW_KINDS 的草稿，服务端重新计算当前冲突报告后校验 token；有冲突、待补充项或报告不完整必须明确勾选。来源变化、过期版本返回 409。前端展示准确内容、实际冲突与未知信息；禁排展示甲的 14 天发生预览。内容未读取、版本不符或报告失败时禁止批准，拒绝仍可用。丢响应重试保留同一决定、参数和请求键。

自动验证见 `test_conversation_constraints.py`、`test_agent_interactions.py`、`AgentApproval.test.tsx` 和 `b-interaction.spec.ts`。这些使用隔离合成资料及测试模型，不作为真实自然语言或个人课表准确率验收。

包含时间事实 commit_import 的多动作批准在任何写入前拒绝（409），界面禁止批准并提示先拒绝再逐项提出，避免第一个保存使第二个冲突 token 失效而留下部分结果。模型提示同样要求逐项批准。两个事实、与任务更新的两种顺序、未知校区且 complete=true 的确认门禁均有真实 Graph/SQLite 回归。
