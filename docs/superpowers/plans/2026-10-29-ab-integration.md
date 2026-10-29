# 甲乙分支合并与联调检查 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans in this session. 用户已明确授权新分支合并与联调检查，连续执行；不重新开发整套甲/乙后续功能。

**Goal:** 合并乙方e38054c和甲方cb84277，验证已有功能能否共存及哪些业务已具备真实联调条件。

**Architecture:** 保留双方领域服务和统一事务/版本/草稿确认；只修复合并引起的兼容问题。读取真实接口做跨领域检查，不用固定替身宣称接通。

**Tech Stack:** 原有FastAPI/SQLite、React/TypeScript、pytest、Playwright和macOS原生工具；沿用已安装依赖。

**Spec:** 用户要求“在新分支合并当前分支和person-a-planning-demo2.4.7，查看哪些可以联调”；范围以`docs/roadmap/甲方完成与待办清单.md`、`docs/roadmap/甲乙接口交接清单.md`和乙方`docs/contracts/*-v1.md`为准。

## Global Constraints

- 联调分支`codex/demo2.4.7-ab-integration`；双方原分支不动。可写源码为`/Users/czy/ProjectManagement/agentbuild`；附加工作区仅同步审阅，避免权限导致代码与依赖分离。
- 保留原有.DS_Store、私有配置、资料、备份、依赖与旧App。不推送、PR、付费模型、公开发布或录屏。
- 不把接口可调用、已有投影可用、实际消费已接通、完整验收通过混为一谈。
- 不复制甲算法，不顺带实现T13–T15完整交互；缺少消费适配/个性化/事件触发则写明下一步。
- 正式发布遵循AGENTS与Demo2.2基线；联调候选使用甲方现有VERSION2.4.7，不覆盖归档或虚构基线。

## Review Focus

1. 计划60/实际25且未完成，更正20后剩余任务是否正确；旧估算、保留安排是否又扣一次。
2. 执行/档案/目标写入是否使甲方旧方案与草稿失效，失败是否不改变日程。
3. 计时中确认普通/局部重排是否保护关联，不产生无法结束的计时。
4. 甲方快照、课程分段/新冲突确认能否与乙方周报、自然语言入口共存。
5. 档案/目标的真实存储是否实际进入甲算法；不能仅因模块同时存在就标“已联调”。

## Task 1: 最小合并

Files: `README.md`、`frontend/playwright.pet.config.ts`、`frontend/src/Today.tsx`及自动合并的`backend/app/planner.py`。
Interfaces: 保留ExecutionFeedback和CourseIntervals；浏览器名单取并集；planner保留新的规则/局部重排与乙方来源/计时保护。

- [x] 记录双方SHA与共同基线，保留3处文本冲突证据。
- [x] 解冲突，检查自动合并语义，完成构建与既有全量回归；兼容失败先复现再最小修复。
- [x] 提交带双父节点的合并，不夹带原有.DS_Store。

## Task 2: 真实跨领域检查

Files: `backend/tests/test_ab_integration.py`、必要的原有兼容实现及浏览器联调用例。
Interfaces: `/executions`、`/execution-timers`、`/profile`、`/goals`、`/planning-capacity`、`/planning-options`、`/replanning`、`/replan-drafts`、`/weekly-review`。

- [x] 隔离SQLite中验证执行与更正后的剩余量/未完状态/版本失效；复核计时关联保护。
- [x] 确认后新增甲快照可被乙周报读取且不重复；双方UI入口与冲突确认不退化。
- [x] 探测档案/目标对甲计算的实际消费状态，记录未接线字段和可开始联调项。
- [x] 执行合并后的后端/前端/浏览器检查，扫描SSE连接错误，形成结果矩阵。

## Task 3: 审阅与交付

- [x] 对合并接点与新增兼容修改进行一次独立只读复核，修复重要问题并复验。
- [x] 更新联调报告/README，明确已通过、可开始、仍缺适配和真实样本未验收。
- [x] 若有兼容开发改动，构建实际联合开发预览并验证；正式预检缺基线则保留失败证据，提供App/应用ZIP/源码ZIP/说明/验证/manifest/SHA256。
- [x] 保留本地联调分支，同步附加审阅工作区；不合入双方原分支、不推送。
