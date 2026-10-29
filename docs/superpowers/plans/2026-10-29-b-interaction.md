# 乙方剩余交互 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans。独立B5/B6/B7按dispatching-parallel-agents限定文件并行，主代理统一集成，最后一次fresh只读复核。用户已连续授权开发，不逐步等待确认。

**Goal:** 完成乙方对甲服务的真实消费、对话、主动建议与可恢复协商，同时明确甲计算未交付的边界。

**Architecture:** Resource/Receipt/资料版本/事件，原草稿确认；独立领域服务及router，公共注册和UI挂载统一处理。不复制甲排程或推断未知习惯。

**Tech Stack:** 现有FastAPI、SQLAlchemy/SQLite、React/React Query、pytest、Vitest、Playwright、Swift。

**Spec:** [本轮设计](2026-10-29-b-interaction-design.md)、[乙任务单](../../roadmap/demo2.4-person-b.md)、[原任务书T12–T15](../../roadmap/demo2.2-development-taskbook.md)、[合并接点](../../roadmap/demo2.4.7-ab-integration.md)。

## Global Constraints

- 工作在可写源码`/Users/czy/ProjectManagement/agentbuild`的新分支`codex/demo2.4.7-b-interaction`；保留原.DS_Store，附加检出仅作审阅。
- 正式修改必须草稿确认；版本/幂等/所有者隔离和回滚沿用原机制。
- 不修改甲的planner/constraints/planning_options/replanning算法；档案排序、目标排程、耗时建议生成仍为甲消费责任。
- 不读取个人数据库，不付费模型测试，不推送/PR/上传/录屏；旧预览与资料保留。正式预检缺基线时保留证据，以开发预览交付。
- 后端全量和浏览器测试前先完成frontend build，不并发删除dist。检查完整退出码与失败数，不能只匹配passed子串。

## Review Focus

1. 跨年/周/时区、模糊下午、重复规则边界与修改同一意图；拒绝默认钟点或静默存私事。
2. 已确认事实、锁定/完成/计时关联、来源变化、同案/无解、重复选择与取消必须保持正式日程安全。
3. 多目标共享容量、暂停、未知投入与真实上限，不能重复承诺容量或推断剩余预算。
4. 建议去重、稍后、跨午夜安静窗口、禁用类别、用户隔离、事实消失再出现；不因无关版本更新反复提醒。
5. 下周草稿生成/确认/失效/恢复、丢响应重放，周报原始快照与执行更正不能被重写。

## Task 1: B5目标容量与复盘采纳

Owned: `goal_capacity.py/goal_capacity_routes.py`、既有`review_contracts.py/review_routes.py/weekly_review.py`、`Goals.tsx/WeeklyReview.tsx/*-state.*`及独立测试/契约文档。不得触碰公共注册、甲算法或其他域。
Interfaces: `goal_capacity_router(get_db,current_user)`；GET `/api/goal-capacity`；复盘新增显式生成下周计划草稿接口，复用甲服务，UI使用原PlanReview。

- [ ] 隔离真实服务RED→GREEN：6小时共享上限、10小时预算、暂停不占预算；未知/过期/跨用户。
- [ ] 接受复盘意向后生成下周草稿、版本拒绝、幂等、确认后的真实状态/快照；恢复不删日程。
- [ ] 完成UI与状态测试，交父代理集成真实浏览器流程；甲个性化/耗时生成缺口明确记录。

## Task 2: B6主动建议

Owned: `proactive_contracts.py/proactive.py/proactive_routes.py`、`ProactiveSuggestions.tsx/proactive-state.*`、独立测试与契约。
Interfaces: `proactive_router(get_db,current_user)`；设置、刷新、列表与版本动作。导出`ProactiveSettings`和`ProactiveSuggestions`，父代理挂载。

- [ ] RED→GREEN：真实风险/容量、20分钟真实空档、同因去重、无关版本变化、稍后/关闭/安静时段与重启。
- [ ] 采纳只打开详情或生成甲草稿；临期/过期/运行/未知均有依据，来源变更重算，不自动写日程或发声音。
- [ ] 完成UI与纯状态测试，不采集其他App行为，无第二套Key。

## Task 3: B7可恢复协商

Owned: `negotiation_contracts.py/negotiation.py/negotiation_routes.py`、`NegotiationPanel.tsx/negotiation-state.*`、独立测试与契约。
Interfaces: `negotiation_router(get_db,current_user)`；`/api/planning-intents`创建/读取/修改、预览、选择与取消；暴露服务函数供父代理agent工具调用。

- [ ] RED→GREEN：同意图多轮修改、来源过期、保留块、已有硬约束保护、两个真实不同方案/同案去重/无解。
- [ ] 临时条件调用甲算法而不写正式约束；选择生成原计划草稿，重复选择不双写；取消、刷新、重启保留已确认事实。
- [ ] 完成界面、状态测试与字段交接，不假装甲服务能生成当前未提供的方案。

## Task 4: B3对话与冲突校对

Owned parent: 新增`conversation_constraints.py/*_routes.py/*_contracts.py`、既有`agent.py`、`Chat.tsx`、独立测试。
Interfaces: 可恢复约束意图和澄清接口、甲约束草稿/预览/确认；新增agent只读/候选工具，冲突预览token随批准参数校验。

- [ ] RED→GREEN：周三下午追问→14–17点→同一意图/草稿，周/时区跨年、无私人事由、重复和重启。
- [ ] 对话查询/创建/修改调用本轮真实领域服务；模型不能自行批准；过期token拒绝，取消不新增规则。
- [ ] 完善T09建议消费界面与契约；真实生成接口缺失则明确未应用，不能伪造样本或效果。

## Task 5: 统一集成与交付

Owned parent: `main.py/App.tsx/Settings.tsx`、公共导航、API生成、e2e、README/报告与本地预览。

- [ ] 核对每个域实际代码、挂载、API生成与所有者/版本契约；测试完整人机流程和错误恢复。
- [ ] 后端/前端/浏览器/原生/冻结回归，读取退出码/失败数；一次独立复核后测试修复重要问题。
- [ ] 更新实际验收矩阵，标清甲剩余消费和外部真实样本；提交本地分支，不推送。
- [ ] 构建真实开发App、应用与源码ZIP、说明/日志/manifest/SHA256；签名/隐私/完整性验证成功后才整理指定缓存，同步审阅检出。
