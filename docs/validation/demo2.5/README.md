# Demo2.5 验证记录

当前开发分支`codex/demo2.5-app-ui-naiwa`。本轮已完成全量界面回归和真实素材App验收，正式归档尚在进行。[进度表](../../roadmap/Demo2.5-开发进度追踪表.md)继续区分实现、当前构建与外部验收。

最新快照见[V1-verification-summary.json](V1-verification-summary.json)，日志哈希随文件保存；B1文件保留为早期检查点。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 后端及脚本 | 681通过，20子测试 | [日志](V1-backend.txt) |
| 前端 | 103通过，类型/构建通过 | [日志](V1-frontend.txt) |
| 新导航下的全部业务与独立导入 | 65通过 | [日志](V1-browser.txt) |
| 本地首次启动竞态与资料复用 | 1通过，已观察RED→GREEN | [日志](V1-local-session.txt) |
| 扩展 | 6通过，类型与指定华工配置构建通过 | B1及最终归档记录 |
| 素材工具与发布脚本 | 36通过，15子测试 | [日志](N-tooling.txt) |
| 原生逻辑/缓存/坐标/状态 | 通过 | [日志](N-native.txt) |
| 原生HTTP | 10场景通过 | [日志](V1-native-http.txt) |
| 实际App与真实NaiWa素材 | 通过，qa_asset_fixture=false | [日志](N-app-real.txt) |

[实际待机图](N-state-idle.png) · [思考状态](N-state-thinking.png) · [待确认状态](N-state-approval.png) · [休息状态](N-state-sleeping.png) · [短测性能](N-pet-playback-profile.json)。性能记录只包含本机原生进程，排除独立WebKit进程，不能当作整机或长期结论。真实角色来源及许可依据的层级见[来源记录](../../../campus-pet/art/naiwa/SOURCES.md)。

自动化保留了原执行、计时、冲突校对、调课/校历、偏好、目标、协商、容量与重排等数据断言。学校采集使用隔离合成样本，原生开页单元测试使用明确替身；不能替代本人当前Chrome/Edge真实学校往返。真实OCR30份/5布局/95%准确率、多物理显示器、长期使用及其他平台仍未验收。正式构建、冻结后台、签名和ZIP检查以本版归档为准。
