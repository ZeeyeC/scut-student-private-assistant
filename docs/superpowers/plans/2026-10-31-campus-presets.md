# Campus period presets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. User specifically requests Antigravity CLI（gemini-4-argon-medium，effort medium） as implementer; invoke it on sanitized source, review and validate returned changes here.

**Goal:** 按已确认位置增加三校区节次选择，预览暂存、确认课程时原子保存，设置页仍可自定义。
**Architecture:** 后端单一可信模板来源，设置/三种课表payload存可选preset；只读预览用派生设置，确认新token后落库；前端共用selector，导入前隐藏。
**Tech Stack:** Python/FastAPI/Pydantic + React/TypeScript。
**Spec:** docs/superpowers/specs/2026-10-31-campus-presets-design.md

## Task1 Gemini测试与实现
- [x] Antigravity CLI（gemini-4-argon-medium，effort medium）先写相关失败测试；本项目确认RED。
- [x] Antigravity CLI（gemini-4-argon-medium，effort medium）实现模板、原子预览/保存与三类校对/设置位置；检查差异、同步schema，相关测试GREEN。

## Task2 验证与发布
- [x] 全量回归及一次独立只读审查，重要问题RED→GREEN。
- [x] 2.5.4独立构建/打包/校验、更新进度、沿原数据打开新版；真实课表保存由用户确认。
