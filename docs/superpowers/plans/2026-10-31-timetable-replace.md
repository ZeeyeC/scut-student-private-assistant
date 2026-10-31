# Timetable replacement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 空课表也可重新核对后保存，学校重新导入提供明确覆盖选项。
**Architecture:** Timetable.save_mode；新冲突token保护完整替换事务；保留旧无token保护；UI模式/预览/确认共用DraftActions。
**Tech Stack:** FastAPI/Pydantic/SQLite + React/Playwright。
**Spec:** docs/superpowers/specs/2026-10-31-timetable-replace-design.md

## Task 1 后端
- [x] 测试复现空表settings变更后鲜token仍409、显式替换未删除旧课程的RED。
- [x] 实现模式、预览数量和实际相同删除语义；测试无token/空捕获/预览后变更保护、默认合并/幂等及保留任务固定事项。

## Task 2 App交互与发布
- [x] 先写UI覆盖/旧设置重试/编辑保留/模式切换后重查/新学校会话测试RED，再实现checkbox、明确确认及重新导入入口。
- [ ] 同步OpenAPI、2.5.3版本/说明/README/进度；针对回归与独立只读审查。
- [ ] 正式发布全部门禁/签名/隐私/哈希，保留旧包；以原资料打开新版，不自动确认真实课表。
