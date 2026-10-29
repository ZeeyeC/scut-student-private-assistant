# 执行计时 v1

乙侧已实现，甲方执行汇总及事件消费联调待完成。复用execution-v1的目标、归属、版本、幂等回执和更正链，无新增数据库。

## 接口

- POST `/api/execution-timers`：ExecutionTarget，包含client_operation_id、execution_id、task_id/task_revision、可选step_id/step_revision、plan_block_id/plan_block_revision、performed_on、timezone和legacy_resolution。绑定具体安排，或明确覆盖/独立投入；不能复用已有事实的执行ID。
- GET `/api/execution-timers`：本人计时Resource列表。status为running/paused/interrupted/finished/discarded；包含elapsed_seconds、confirmed_elapsed_seconds、target和segments。读取不修改资料。
- POST `/api/execution-timers/{id}/actions`：revision、client_operation_id、action=heartbeat/pause/resume/finish/discard；写入均需Idempotency-Key。finish还需feedback，可给unfinished_reason、task_status及当前task_revision；可明确给actual_minutes，改为手工补记并替代同次计时。

## 时长与恢复

采用服务器单调时钟，按秒持久化，先合计秒数再转换整数分钟；两个59秒记录汇总为118秒/1分钟，原秒数保留。墙钟回退不产生负投入。暂停期间不累计。同一用户仅允许一个有效运行计时，同一安排不允许多份未结束计时。

前端每15秒确认连接，租约120秒。失联超过租约、服务器实例变化或单调时间无效时，视为interrupted，仅保留最后持久化确认值；不把离线间隔自动计入。用户可以继续、结束或改补记。该选择是异常退出保护规则，不是用户习惯推断。

开始、暂停、继续、结束、放弃和检测到中断会改变资料版本；正常心跳仅改变计时状态版本，避免每15秒使草稿失效。结束才形成权威execution事实，沿用execution_changed事件；状态通知使用execution_timer_changed。正式日程不自动移动。

结束后计时来源为timer，保存actual_seconds、actual_minutes、timer_id；手工替代来源manual，保留计时历史但不再累计其旧值。后续分钟更正来源manual，按明确输入重新计算秒数，旧精确记录仍保留。未执行/跳过不能保留非零计时，需明确改为补记0。

ExecutionSummary新增可选actual_seconds及unconfirmed_execution_ids；已记录投入与未确认缺口分别表达。历史无精确秒数字段的记录按其已确认分钟换算，仍保留原来源。

删除任务级联计时资源；有未结束计时的步骤拒绝重新拆解。丢失响应重试复用回执键与操作ID，结束不会重复建事实。没有自动采集其他App行为、后台模型调用或独立Key配置。

开始阶段只校验旧估算的覆盖选择，不创建/修改估算基线；结束产生执行事实时才原子应用替代，放弃计时不清除历史估算。`skipped/not_started`与正数手工分钟在请求边界返回422，允许界面修改后再提交。

既有计时始终保留开始时确认的执行日期与时区；修改设置时区不会阻止其结束或改为补记，新建直接补记仍需匹配当前设置。现有计划若会删除未结束计时所绑定的安排，确认返回409并提示先结束/放弃计时后重新生成；检查发生在保存快照和替换安排前，不静默解除关联或丢失投入。
