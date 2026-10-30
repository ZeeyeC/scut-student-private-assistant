# Demo2.5 当前验证记录

当前为开发中的U1/U2/B1阶段，尚未生成Demo2.5正式App或归档。[进度表](../../roadmap/Demo2.5-开发进度追踪表.md)区分代码实现、自动化验证与外部验收。

首轮实现快照见[B1-verification-summary.json](B1-verification-summary.json)，各日志SHA256随该文件保存。

| 检查 | 当前结果 | 证据 |
| --- | --- | --- |
| 后端及脚本 | 657通过，20子测试通过 | [B1-backend.txt](B1-backend.txt) |
| 前端单元 | 103通过，类型与构建通过 | [B1-frontend.txt](B1-frontend.txt) |
| 新工作台与独立导入流程 | 7通过；使用真实API与合成学校/原生桥接替身 | [B1-browser.txt](B1-browser.txt) |
| 扩展 | 6通过，类型与生产构建通过 | [B1-extension.txt](B1-extension.txt)、[类型](B1-extension-types.txt)、[构建](B1-extension-build.txt) |
| 原生逻辑 | 通过，包括Chrome/Edge选择、失效上下文及旧后台拒绝 | [B1-native.txt](B1-native.txt) |
| 原生HTTP健康 | 10场景通过 | [B1-native-http.txt](B1-native-http.txt) |

浏览器流程覆盖：旧导航映射、320/390px、任务草稿确认前不保存、抽屉关闭保留输入、五组设置、原生导航与嵌套抽屉交错、无App Cookie的外部采集回传、URL授权清除、扩展缺失/取消失效、实际桥接脚本调用与双击去重。

尚未完成：旧版全部浏览器交互选择器迁移及全量执行、当前实际Mac App界面/冻结后台验证、NaiWa素材授权与正式接入、真实学校Chrome/Edge扩展完整流程及其他设备验收。自动化中的学校采集与原生开页替身不代表上述外部验收。旧Demo2.4.9结果也不代替新版结果。
