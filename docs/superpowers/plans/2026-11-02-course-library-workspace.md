# 课程资料独立页面 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增可浏览全部已上传资料、按课程筛选和修改分类的独立页面；助手置顶、其余四入口分组、设置固定底部。

**Architecture:** 保留Resource知识来源与私有原件，不迁移数据。新增摘要列表与版本化分类修改；React独立页复用原解析/检索，source_id跨页带入聊天但不自动发送。原生导航与前端同步。

**Tech Stack:** 现有FastAPI/SQLite/SQLAlchemy/Pydantic、React/TypeScript/TanStack Query、Swift/AppKit/WKWebView；不新增运行框架。

**Spec:** docs/superpowers/specs/2026-11-02-course-library-design.md；批准预览docs/design/course-library-v1/reference.html。

## Global Constraints
- 正式目标2.9.0，分支codex/course-library-workspace；同一隔离工作树执行，个人资料/Key/备份/依赖不动。
- 助手独立置顶，40px分隔；下方今日/日程/任务/课程资料，设置固定底部；只内容滚动。
- 独立资料页按批准预览实现；一份资料先关联一门课程，未关联归未分类；已有网页保存/正文检索能力仍可达。
- 原资料不复制/重新上传，列表不返回全部正文或内部storage_name；缺元信息显示未知，不编造。
- 按版本独立构建、完整验证；旧版先云端核验再整理，固定入口指向新版。不调用付费模型。

## Review Focus
- 旧资料没有size_bytes、关联课程已删除或重名：显示真实状态，不漏文件、不按名称合并课程ID。
- 分类并发/失响应重试：revision+幂等，不重复副作用；外部用户资料和课程不可操作。
- 页面跳转时迟到详情/附件结果：旧响应不能改选新文件或新聊天，选用需本人发送。
- 上传多文件部分失败/取消：成功项可见、失败可重试，不误称全部成功，不重复入库。
- 窄窗口、长文件名、课程数量多：不溢出，侧栏固定，弹窗和确认按钮可达。

### Task 1: 摘要与分类接口
**Files:** backend/app/knowledge_library.py、knowledge_contracts.py、knowledge.py、knowledge_routes.py；backend/tests/test_knowledge_library.py。
**Interfaces:** GET /api/knowledge/library?course_id=&unclassified=&query=&sort=newest|name&offset=0&limit=50 → {items:Resource摘要[],total,all_count,courses:[{id,name,count,missing}],unclassified_count}；摘要data含filename/title/format/course_id/course_name/course_missing/size_bytes/created_at/source_type/url/chunk_count/truncated，不含chunks/storage_name。PATCH /api/knowledge/sources/{id}/course body{revision,course_id|null}，幂等键，返回{id,revision}。
- [x] 写失败测试：已有文件/网页摘要、缺元信息、过滤/分页/课程计数、重名和已删除课程；分类所属校验、409、重试、忙碌/失效隔离。
- [x] 运行pytest确认RED；实现摘要/受控stat、上传记录size_bytes、分类事务和隐私代次；运行知识库/备份相关测试GREEN。
- [x] 提交可追溯代码与验证记录。

### Task 2: 独立资料工作区
**Files:** frontend/src/KnowledgeLibrary.tsx、knowledge-library.css、knowledge-library.ts、KnowledgeManager.tsx（缩为选择器）、Chat.tsx、Settings.tsx；frontend/e2e/knowledge-library.spec.ts。
**Interfaces:** KnowledgeLibrary({onUseSource:(id:string)=>void})；现有KnowledgeManager作为轻量选择器保留选用/正文检索；上传/完整管理移入独立页。文件详情复用GET source；归属修改PATCH；上传保持原幂等键，错误明确。
- [x] 写独立页E2E失败用例：全部文件/课程筛选、详情修改归属、选用切换助手但不自动发送、聊天上传跨会话可见、部分失败重试、窄窗口。
- [x] 实现匹配预览的列表、上传对话框、详情抽屉，保留网页保存/正文检索入口；设置改为跳转管理。运行针对E2E与类型检查。

### Task 3: 导航与原生联动
**Files:** App.tsx、layout/AppShell.tsx、layout/navigation.ts、layout/workspace.css；campus-pet/Sources/AppDelegate.swift、Resources/Bridge.js；对应TS/Swift/tests。
**Interfaces:** PageId增加knowledge；NavigationTarget在assistant可携带sourceId，knowledge可携带courseId。选用资料通过导航状态一次性消费，返回聊天不重复附加；ID由API重新校验。导航总入口6个，主导航语义覆盖全部可见入口以兼容既有操作。
- [x] TS/Swift导航用例先RED；实现助手顶部独立分组、四常用项、底部设置、原生映射；既有提醒/审批导航保留。
- [x] 运行单元与原生检查；维护旧导航兼容，检验跨页迟到请求边界。

### Task 4: 设计对照与发布
**Files:** 新设计参考manifest/视觉验证脚本、frontend/e2e/knowledge-library.spec.ts及现有视觉用例、scripts/release-macos.py、VERSION、README、docs/releases/Demo2.9.md。
- [x] 从批准预览生成独立只读参考截图，不从实现截图反向建立参考。旧页面仅导航区域按新参考验收，正文与桌宠继续对照旧已接受参考；禁止忽略未批准的正文变化。
- [x] 完成一次独立代码审查并修复Important/Critical；前后端针对检查与完整门禁通过后独立发布2.9。
- [x] 实际WKWebView验证上传/分类/选用/侧栏滚动，原资料无参数恢复与私密值扫描；不把合成模型当真实识别效果。
- [ ] GitHub同步源码与验收，旧2.8.1完整包上传原私有Releases并下载SHA校验后清理旧副本；固定入口切换2.9，保留源码/配置/资料/备份/依赖。
