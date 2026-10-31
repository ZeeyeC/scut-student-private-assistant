# Dock应用入口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 普通App的Dock入口在窗口/桌宠隐藏后仍可发现和恢复。
**Architecture:** 构建LSUIElement=false + AppDelegate regular；保持既有重开、菜单栏和退出语义。
**Tech Stack:** Swift/AppKit, Python构建。
**Spec:** docs/superpowers/specs/2026-10-31-dock-presence-design.md

## Task 1
- [ ] 编写系统级Dock资格检查，在运行的2.5.1上确认RED；补充实际原生窗口生命周期断言。
- [ ] 修改AppDelegate.swift及build.py；更新VERSION、README、2.5.2说明与进度。
- [ ] 独立审查改动，运行正式发布全量门禁（沿用2.5.1视觉基准以证明GUI未变）；不改个人数据库。
- [ ] 校验归档、退出原实例并用原资料打开2.5.2，系统级Dock检查GREEN；提交同步并记录结果。
