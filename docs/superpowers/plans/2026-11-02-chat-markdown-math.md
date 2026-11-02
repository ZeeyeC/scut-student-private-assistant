# Chat Markdown and Math Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox syntax. User has authorized execution and prefers Antigravity Argon Medium for implementation; use sanitized context, then integrate and verify locally.

**Goal:** 助手回答正确显示Markdown和数学公式，并保持即时流式显示与现有App风格。

**Architecture:** 用独立AssistantMarkdown组件接管助手Text分支，用户Text分支保留原样。remark处理GFM和公式，rehype-katex本地渲染；组件配置限制外部资源与原始HTML，CSS局部控制布局。

**Tech Stack:** React19 / TypeScript / assistant-ui / remark-gfm / remark-math / rehype-katex / KaTeX / Playwright。

**Spec:** docs/superpowers/specs/2026-11-02-chat-markdown-design.md

## Global Constraints

- smooth=false；不依赖requestAnimationFrame显示已收内容。
- 原始HTML不执行，链接限定HTTP/HTTPS与页内锚点，图片不自动加载，KaTeX trust=false。
- 消息原文和业务接口不变；无付费业务模型调用；旧版本与私有配置保留。
- 每版独立构建；本版2.9.2，失败不覆盖已有发布。

## Review Focus

- 符号拆成多个流片段时仍能继续显示，关闭/中断流后可读。
- 代码中的美元、反斜杠与数学分隔符必须保留。
- HTML/危险URL/图片及KaTeX链接宏不产生执行或外部请求。
- 长表格/公式/链接在窄窗口不撑宽页面。
- 历史消息和用户原文显示保持兼容，代码复制得到原内容。

### Task 1: Renderer and chat integration

**Files:** frontend/src/AssistantMarkdown.tsx, frontend/src/assistant-markdown.css, frontend/src/Chat.tsx, frontend/package.json, frontend/package-lock.json; frontend/e2e/chat-markdown.spec.ts; frontend/playwright.pet.config.ts.

**Interfaces:** AssistantMarkdown(): JSX element consumes assistant-ui text-part context; exposed only as AssistantMessage Text renderer. URL policy and math preprocessing remain local.

- [x] Write isolated E2E tests injecting synthetic SSE message events into real ChatPage: strong/list/table/code/math, original user text, streaming chunk completion, paused animation frames, unsafe content/no requests, narrow overflow, history replay and code copy.
- [x] Run against baseline build and observe missing-format assertions fail.
- [x] Install pinned compatible dependencies; Antigravity generates narrow renderer/CSS with sanitized context and no data/keys. Main assistant reviews and integrates, retaining smooth=false.
- [x] Run targeted E2E, frontend typecheck/unit suite and build; require all pass. Review code/libraries and exercise delimiter/code boundaries.
- [x] Commit implementation with tests and license materials.

### Task 2: Review, native acceptance and release

**Files:** campus-pet/VERSION, README.md, docs/releases/Demo2.9.2.md, docs/validation/demo2.9.2, progress table, OpenSource notices.

**Interfaces:** Task1 consumes no backend changes; final App includes built frontend, fonts and license files.

- [ ] Fresh whole-branch review against spec, resolve material findings with meaningful failing regressions.
- [ ] Update2.9.2/version/docs/progress. Gracefully quit currentApp for5173 isolated checks, preserve data identity.
- [ ] Run scripts/release-macos.py --version2.9.2 --workspace /Users/czy/ProjectManagement with existing validated PET_EXTENSION_BROWSER and temporary caffeinate -i.
- [ ] Require19 gates and signature/ZIP/SHA/private scans; use finalApp isolated synthetic session for native Markdown/math display then restore original data.
- [ ] Update stable App link, preserve old releasedApp and failed logs; clear known generated caches only after success, restore regenerated historical evidence; commit completion evidence locally.
