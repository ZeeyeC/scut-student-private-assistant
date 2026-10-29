# 甲 A3：容量读取与规划契约增量

Demo2.4.4在每周硬禁排基础上提供T06的基本容量接口，不代表A3全部完成，不提前宣称A4–A6已交付。用户要求功能完整但不做过度细化，同时不破坏双人协议。

## 接口

`GET /api/planning-capacity?scope=today`按保存时区计算今天剩余时间；不允许指定其他日期或多日。`GET /api/planning-capacity?scope=range&horizon_days=7`默认当前当地日期起7天，也可显式提供target_date及1–7天范围，不能规划过去。需原会话认证，按本人资源隔离。成功200，非法范围422，未登录401；查询无需幂等键，没有正式写入、快照、回执或新草稿，也不使已有草稿失效。

报告带schema_version=1、source_revision（全局资料版本）、rule_version、calculated_at、时区与范围。响应示例的核心字段：`{capacity_upper_bound_minutes:90, required_minutes:180, reserved_work_minutes:0, proposed_minutes:90, unallocated_minutes:90, unknown_estimate_count:1, changes:{added:2,retained:0,removed:0}}`。days逐日含真实带时区free_windows、free_minutes、budget_remaining_minutes、capacity_upper_bound_minutes、proposed_minutes；unscheduled保留原步骤/任务ID、未知或数值分钟及原因，warnings保留锁定/历史/依赖冲突。

容量上限是扣除实际课程占用、固定事项及缓冲、展开后的硬禁排和保留块后的时间与每日预算的较小值。它不是承诺可完成分钟；截止、依赖和最短时间块可使proposed_minutes更小。required_minutes为所有开放步骤的预计剩余工作，扣除已记录spent_minutes及有效保留安排预留后仍需分配的部分；不将未反馈实际投入推断为0，也不根据计划长度生成实际分钟。此版本仍消费已有步骤分钟字段，尚未对接乙的独立执行汇总。reserved_work_minutes可能包含范围外保留安排，报告明确说明；unknown_estimate_count仅指尚无可排程步骤的开放待办。unallocated_minutes是已知工作未排分钟，不含未知估时。

`changes`表示按当前普通规划规则重算的增加/保留/移除数量，不承诺是最少移动方案，也不实际执行。GET报告与`POST /api/plan-drafts`统一调用`planning_result`；每次计划payload新增capacity，并通过已有哈希、资料版本、确认与快照事务保存。旧草稿没有capacity仍兼容；算法规则版本不变，禁止把报告直接写成正式计划。乙的目标预算、风险或协商展示可读取本接口，事实变化后必须重新查询，并通过原草稿确认机制写入安排。

## 边界及后续

独立PlanningCapacity组件仅由甲的SmartSchedule挂载；本轮不改公共Today/App/Settings/types/style、乙的agent/tasks/Chat/TaskDetail或原生桌宠，不定义另一套执行记录或个人档案。新增领域模块planning_capacity.py用于响应契约和汇总，不另写一套排程计算。API统一生成，无依赖升级。

18项后端场景、2条浏览器流程使用隔离合成资料与固定时间；冻结后端验证真实打包接口。正式目录日志/manifest记录整包结果。无真实OCR准确率声明、付费请求、PR或录屏。已知S02取消清理仍由乙处理。

顺序：先继续A3软偏好/必要方案契约，再推进A4受影响范围与最少调整。执行重排的最终验收必须接乙的权威实际投入、来源更正和变化事件；A5排序与减负必须接已确认档案/目标，接口缺失可用明确测试替身推进甲服务，但不能据此将最终端到端标记完成。学校校历、实践周与30份真实匿名OCR样本缺口也须保留。

用户已授权每小时本对话自动续作直到A6完成后停用。自动任务ID `a6`，不是另一个开发工作区；继续时读取本文件和最新阶段记录，不覆盖个人配置，不重复开发已经发布内容。
