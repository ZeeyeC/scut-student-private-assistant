# 扩展安装引导与独立发布实施计划

> 执行方式：superpowers:executing-plans，自行实施，完成后一次独立审查。

Goal：一个App包即可提供扩展与首次安装引导，并验证无源码环境。
Spec：[设计](../specs/2026-10-31-extension-onboarding-design.md)。用户已批准方案并明确要求直接实现和打包，不再等待重复确认。

## 约束

保留现有视觉基准和全部业务保护；只为导入的显式操作打开指定Chrome/Edge。保留用户.DS_Store改动。2.5.1尚未发布，继续用该版本；新包必须独立构建，不复制旧App；不付费模型、不公开上传、不登录真实学校。

## Review Focus

1. Edge选择与未安装浏览器：管理页和导入必须同一个指定浏览器。
2. 浏览器关闭/会话取消/过期：自动检测停止，不重开学校或延长授权。
3. 旧扩展：明确更新/重新加载指引，不错报为已安装可用。
4. 无源码/空资料目录：扩展从包中释放，路径稳定，旧私密配置不打包。
5. 新聊天修复与原生待办：完整回归，不把旧验收当新版通过。

### Task 1：安装引导与固定原生动作
Files：SchoolImportPanel.tsx、新ExtensionSetup.tsx、SchoolImport.swift、BrowserLaunchPolicy.swift及原生/Playwright测试。
- [x] 先写缺扩展自动展开、管理页指定浏览器、复制固定路径、关闭重开保留状态测试，确认RED。
- [x] 实现固定管理页native命令、原生复制、三步引导；不接受任意URL/路径参数。
- [x] 对应测试GREEN，提交并更新追踪表。

### Task 2：连接恢复与更新提示
Files：SchoolImportBridge.tsx、extension/entrypoints/app.content.ts、desktop_import_bridge.py、现有导入E2E。
- [x] 缺扩展→模拟安装→自动继续、过旧能力→提示更新、取消不复活用例RED。
- [x] 有效导入页自动检测，能力版本反馈，不重复start/学校页；回传仍App确认。
- [x] 流程回归GREEN，提交。

### Task 3：独立发布模式及新用户模拟
Files：campus-pet/build.py、scripts/release-macos.py、发布测试、新独立用户验证脚本。
- [ ] 发布包含开发标记/无源码无法释放扩展的检查RED。
- [ ] 正式构建显式release模式去开发标记；验证临时资料根、扩展manifest/哈希和新App隔离启动。
- [ ] 真实浏览器尝试仅在独立测试profile安装；不能操作用户日常profile。受工具/浏览器限制则如实记录，模拟结果分列。

### Task 4：全量验证、独立审查与2.5.1打包
- [x] 补齐前轮聊天修复后的完整原生/界面回归、扩展与后端/脚本测试及10张视觉基准。
- [x] 一次全分支独立审查，2项Important均RED→GREEN；1项Minor暂缓。
- [ ] 更新VERSION/README/说明，运行release-macos.py --version 2.5.1，验证App/ZIP/源码ZIP/manifest/SHA，无私密资料。
- [ ] 更新追踪表和实际用户体验记录；保留真实学校/OCR/多物理显示器缺口。
