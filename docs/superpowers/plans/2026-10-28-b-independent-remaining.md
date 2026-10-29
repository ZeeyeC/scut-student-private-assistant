# 乙方剩余独立功能 Implementation Plan

> **For agentic workers:** 使用superpowers:executing-plans逐项执行；独立的S02和T07按dispatching-parallel-agents限定文件并行。用户已要求连续执行，并确认甲方尚未交付，先完成独立功能。

**Goal:** 在B1后补齐可靠计时、取消清理、确认档案、目标管理、可追溯周统计与建议交互；所有需要甲方新服务的能力保持明确待联调。

**Architecture:** 复用Resource/Receipt、全局版本、planning_event与plan_snapshot。计时按秒保存，使用服务器单调时钟和连接租约，仅结束时形成权威执行事实；档案和目标独立存储，统计读取现有不可变快照及更正链。领域服务及路由独立，公共注册统一集成。

**Tech Stack:** 既有Python3.12/FastAPI/SQLAlchemy/SQLite、React/TypeScript/React Query、pytest/Vitest/Playwright；不升级依赖或新增模型配置。

**Spec:** [乙方路线](2026-10-28-demo2.4-b-roadmap.md)、[原任务书T07/T08/T10/T12–T15/S02](../../roadmap/demo2.2-development-taskbook.md)。用户补充：甲T04/T06/T11尚未交付，先完成独立功能。

## Global Constraints

- 工作在可写源码目录`/Users/czy/ProjectManagement/agentbuild`的`codex/after-demo2.4-execution`，附加只读工作区仅同步审阅提交；保留原有.DS_Store改动。
- 缺记录为未知，历史估算不能升级成真实计时；桌宠完成不伪造分钟。
- 计时暂停不计时，结束重试不重复；进程重启或失联不无限累计，未确认间隔可事后补记。
- 正式安排修改仍经草稿确认。甲方容量、重排、多方案、重复约束尚缺时明确不可用，不在乙侧复制算法，不用固定测试替身宣称端到端通过。
- 不调用付费模型，不操作个人数据库，不推送/PR/公开上传/录屏。正式发布仍须满足AGENTS和Demo2.2基线检查；缺基线时保留开发预览与失败证据。

## Review Focus

1. 心跳与暂停/结束竞态、掉线/重启/时钟变化：只保留已确认秒数且重放不重复。
2. 计时改补记或后续更正：只保留一个有效逻辑执行，汇总秒数后再转换分钟。
3. 取消异常期间事务释放：取消继续传播、连接已归还、下次写入可用。
4. 未设置/过期档案、暂停目标、未知容量：保持未知或停用，不能造默认习惯或偷偷新增安排。
5. 周统计的缺记录、历史估算与快照变更：数值可追溯、重排与更正不重复，数据不足不归因为自律。

## Task 1: S02取消清理

Files: `backend/app/db_sessions.py`、`main.py`、`agent.py`、`backend/tests/test_request_cancellation.py`。
Interfaces: `sqlite_transaction(sessions)`与`session_scope(sessions)`提供原有事务/读取语义；仅清理阶段屏蔽取消，退出继续传播。

- [x] 用真实SQLite/ASGI断连写失败用例并观察连接未归还。
- [x] 按根因修复rollback/close，不吞异常、不扩大业务屏蔽范围。
- [x] 验证断连、刷新、task.cancel、关闭服务和后续写入，跑原agent/删除回归。

## Task 2: B2计时领域

Files: 新增`backend/app/execution_timers.py`、`timer_contracts.py`、`timer_routes.py`、`backend/tests/test_execution_timers.py`；修改`execution.py/execution_contracts.py/tasks.py/deletion.py`与最小main注册。
Interfaces: `timer_router(get_db,current_user,boot_id)`；`POST /api/execution-timers`、`GET /api/execution-timers`、`POST /api/execution-timers/{id}/actions`，动作heartbeat/pause/resume/finish/discard。目标沿用执行契约；命令带revision、client_operation_id；结束可显式改为手工分钟并保留原计时来源。

- [x] 写计时10分钟、暂停15分钟、继续15分钟、结束实际25分钟且任务未完的API断言；观察RED。
- [x] 写结束/心跳重放、同用户单运行计时、不同来源互斥、59+59秒汇总、失联/boot变化/时钟回退、删除/拆解关联回归。
- [x] 实现服务器单调时钟计时及120秒连接租约；UI每15秒心跳。心跳更新状态版本，开始/暂停/结束等变化更新全局资料版本；失联后仅保留最后确认值。
- [x] 结束事务追加execution事实和事件；计时改补记与后续更正不双计。运行新增测试及B1全部回归后提交。

## Task 3: B2界面与迁移

Files: 新增`frontend/src/ExecutionTimer.tsx`及状态测试、`frontend/e2e/independent-features.spec.ts`；挂载`ExecutionFeedback.tsx`，更新发布测试名单。
Interfaces: `ExecutionTimer({task,step?,block?})`共用真实计时API和查询缓存。

- [x] 编写开始/暂停/继续/结束、刷新保留、失联提示、切换补记和任务未完成的浏览器流程。
- [x] 实现计时状态和独立完成反馈；源数据未加载不启用操作，重试复用操作ID/回执键。
- [x] 验证B1入口和桌宠完成仍不造分钟；合成旧数据与备份恢复保留计时记录。

## Task 4: B4/T07档案

Files: `profile_contracts.py/profiles.py/profile_routes.py`、`test_profiles.py`、`PersonalProfile.tsx`与状态测试；父任务统一挂载Settings。
Interfaces: `profile_router(get_db,current_user)`；GET/PUT `/api/profile`、POST `/api/profile/reset`；确认值、来源、样本量、有效期与版本读取。

- [x] 先测试未知/0、设置与重置、过期、版本/幂等/归属、失败回滚与重启。
- [x] 实现显式档案，不推断习惯；重置不删任务课程；事件与资料版本原子更新。
- [x] 集成设置界面及真实API浏览器流程；甲方排序效果仍待联调。

## Task 5: B5/T08目标管理

Files: 新增`goals.py/goal_contracts.py/goal_routes.py`、`test_goals.py`、`Goals.tsx`。
Interfaces: GET/POST `/api/goals`、PATCH `/api/goals/{id}`、子任务关联与暂停；保留目标周预算/期限/优先级/负荷类别和已完成关联事实。

- [x] 写创建、修改、子任务关联、暂停/恢复、版本/幂等/重启及跨用户失败用例。
- [x] 实现目标CRUD和界面；不自动生成正式任务/安排；缺甲方容量服务时容量明确未知，不能返回伪造的6/10小时结果。
- [x] 交付稳定已确认目标读取与goal_changed事件，验证暂停不新增安排且保留完成事实。

## Task 6: B5/T12独立周统计与改进交互

Files: 新增`weekly_review.py/review_routes.py`、`test_weekly_review.py`、`WeeklyReview.tsx`及建议状态模块。
Interfaces: GET `/api/weekly-review?week_start=`读取原始/最近计划快照、当前安排和有效执行；输出引用、未知/估算及事实缺口。改进建议先保存待确认意图，依赖甲排程时不直接落日程。

- [x] 编写原计划60、实际25、更正20、缺记录、重排快照和跨周边界的固定断言。
- [x] 按当地周和半开区间统计，秒数/更正链去重；缺数据标未知，原始快照不足明确来源缺口。
- [x] 实现可核对原因追问、建议接受/拒绝/恢复；只有已有真实领域服务可应用的动作才提供确认，其他标待甲服务。
- [x] 真实浏览器验证数据、刷新和原任务保留。

## Task 7: 整体验证与阶段交付

- [ ] 逐项复核独立功能及甲方依赖矩阵；B3/B6/B7需要新甲方接口的端到端场景维持未验收。
- [ ] 全后端、前端、浏览器及原生逻辑回归，独立复核并修复重要问题；验证真实冻结App。
- [ ] 更新实际进度/交接契约、开发预览与当前源码ZIP、日志/manifest/SHA256；检查私密资料。正式发布只在基线与联合验收条件成立后执行，不伪造基线。
- [ ] 完成独立部分后继续任何已具备真实依赖的乙方功能；没有依赖时交付明确待联调清单及接口字段，不将全部任务标为完成。
