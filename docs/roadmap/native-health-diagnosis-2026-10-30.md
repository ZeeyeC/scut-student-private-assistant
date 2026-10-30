# 原生健康请求诊断（2026-10-30）

本轮修复可控实验已复现的共享旧连接风险，并新增请求边界证据。后续路径/二进制对照与只读配置检查将当前「新 App 和新测试宿主均 0 连接」定位到 **LuLu 对新程序路径的网络授权边界**，不是生产 helper 的 guard 抽取或源码顺序问题。用户明确要求默认自动允许未知连接、保留既有阻止规则后，主代理按要求启用 LuLu 被动允许模式；HTTP 10 场景全部通过，形成设置前 RED → 设置后 GREEN 的因果证据。后续同源实际 App 完整联调已 passed=true、56项检查、exit0；隔离HTTP与实际App分别留有结果，仍不将其泛化为所有历史间歇超时已经根治。

## 已知失败边界

历史两轮完整 App 在取消停止服务的原生 sheet 后，`verifyHealth()` 的 3 秒请求超时；同时 Python HTTP 返回 200、WebKit/API 工作正常，后台 access log 未见该次 Swift 请求。代码中启动健康检查已先用过 `URLSession.shared`，所以取消 sheet 后是后续原生健康请求，而非进程中第一次使用共享会话。SSE/SQLite 没有被证明是该失败的原因。

本轮先读取请求入口、取消 sheet、停服确认及测试服务器，检查当前系统代理（`scutil --proxy` 返回空字典），然后在随机 `127.0.0.1` 端口运行临时 HTTP 服务和 AppKit 探针。不访问 5173、个人数据库、模型配置或外部模型。

## 可控实验与反证

| 对照 | 实际观察 | 可以支持的结论 |
| --- | --- | --- |
| 健康 HTTP 服务、共享会话与新 ephemeral 会话、取消 sheet | 多组均为 200，通常约 4–34 ms | 取消 sheet 本身不足以稳定触发历史失败 |
| 服务仅在第一次请求后停止读取该旧连接，继续接受新连接 | 共享会话第二次在约 3.006–3.014 秒超时，`reused=true / requestStarted=true / responseStarted=false`；服务只读到一次请求 | 共享连接复用存在可稳定复现的健康探测风险 |
| 同一旧连接场景、每次独立 ephemeral 会话 | 两次均 200，`reused=false`，服务读到两次请求 | 独立连接消除该受控旧连接风险；不证明历史失败同因 |
| 同端口 NWConnection 直接 TCP 对照 | 独立探针约 4–34 ms ready/收到响应 | 普通 loopback TCP 本身可用 |
| 原生回归测试宿主出现 URLSession 超时后，在同一进程立即运行 NWConnection | 两种栈均无服务器请求；URLSession metrics 为 fetch 已开始、DNS/connect/request/response 均未开始 | 不能把此停滞归为 CFNetwork 专属问题，也不能据此替换为自写 HTTP 栈 |
| 上述测试服务器、立即启动独立 NW 探针 | 同端口收到响应，服务器可接受新连接 | 服务器并未停止；差异在程序访问网络之前，后续通过 LuLu 规则定位 |
| 相同 macOS 13 部署目标、不同临时目录/名称、Bundle 配置读取和 MainActor 初始化对照 | 未稳定消除测试宿主的连接前停滞 | 这些尝试不构成已证根因，不保留无用预热或无限重试 |
| 相同 probe 源码，源码顺序 probe/helper/service 与 service/helper/probe × guard 内联/抽取，共四种新产物 | 四种产物的 URLSession 与 NWConnection 均 0 请求；同端口旧原路径 control 在矩阵前后均各收到两次请求 | 排除源码顺序和 guard 抽取；不能通过修改生产 helper 解释路径差异 |
| 复制旧成功二进制到新路径，内容不变（主代理独立执行） | 新路径 0 请求；旧原路径继续毫秒级成功 | 不能归因于编译、链接或 HTTP 实现；应核对路径/程序身份的系统网络授权 |

所有需要监听/连接 loopback 的实验均通过升级后的 `exec_command` Python runner 执行。默认沙箱不允许本地监听，会直接报 `Operation not permitted`；此错误与已升级实验中记录到的 3 秒连接前停滞分开记录。父代理独立升级运行正式 runner 同样观察到 0 请求，保留在本轮本地验证日志中。

## LuLu 授权证据与处置边界

只读 `systemextensionsctl list` 确认 `com.objective-see.lulu.extension` 4.5.3 为 activated/enabled。仅解码 `/Library/Objective-See/LuLu/rules.plist` 中匹配本项目的规则，不导出其他程序的规则或个人配置：

- 旧成功探针有现存用户规则：`path=/tmp/campus-native-health-investigation/probe`，`action=1`、`type=3`、`scope=0`，远端地址/端口为 `*`。
- 若干此前成功的开发 App 路径也有现存 `action=1` 规则；当前新测试路径和新 App 路径不在这些项目允许规则中。
- 相关模式为 `disabled=false / passiveMode=false / blockMode=false / allowLocalHost=false`。因此新程序不会获得 localhost 的自动豁免。LuLu 设置 UI 同样显示「允许 localhost 流量」未勾选；只读查看时未见仍在显示的项目待决警报，短命测试进程已经退出。

[LuLu 4.5.3 官方常量定义](https://github.com/objective-see/LuLu/blob/v4.5.3/LuLu/Shared/consts.h) 将 action 1 定义为 ALLOW、type 3 定义为用户规则、scope 0 定义为进程范围。[4.5.3 过滤实现](https://github.com/objective-see/LuLu/blob/v4.5.3/LuLu/Extension/FilterDataProvider.m) 明确对 IPv4 loopback 进行过滤；localhost 自动放行仅在该偏好开启时生效，未匹配规则的新连接可返回 pause verdict 等待用户。这解释了 URLSession 和 NWConnection 同时停留在发送前，而已有允许规则的旧路径继续工作的结果。debug 级统一日志未提供持久化命中条目，本文没有伪造逐请求 LuLu 日志；因果依据为路径矩阵、实际规则/模式与用户授权修改后的真实 HTTP 结果。

用户随后明确要求「默认自动放行未知联网，只保留阻止部分软件的部分联网功能」。先核实 [4.5.3 规则匹配顺序](https://github.com/objective-see/LuLu/blob/v4.5.3/LuLu/Extension/FilterDataProvider.m#L553)：匹配现有规则后即返回，只有没有匹配规则时才进入 passive 分支。因此主代理通过官方 UI 设置「被动模式 → 允许新连接 → 不创建新规则」，实际读取值为 `disabled=false / passiveMode=true / passiveModeAction=0 / passiveModeRules=0 / blockMode=false`。LuLu 保持运行，localhost 豁免未开启，没有删除规则或覆盖旧已获准二进制路径。已有阻止规则仍先于被动模式处理；新连接默认允许，符合用户明确选择。

主代理在操作前后核对 `rules.plist` SHA256 均为 `1ba720bf82340c7cf8deab25b164d8896f61e66b0faa02ffd035f8124a287065`，证明没有删改既有规则。设置后重新编译和运行稳定 HTTP 宿主，10 场景全部通过：状态 503、坏 JSON、302 和错误身份/新能力均收到真实 HTTP 后拒绝；真实不响应场景有 `requestStarted=true`，约 3007 ms 返回原 `NSURLErrorDomain/-1001`，服务端恰好收到一次请求。这个结果排除了此前「根本未发出请求」被误算为负面场景通过的可能。完整日志由统一验收保留为 `native-health-authorized-green.log`，设置前失败与路径矩阵日志也保留。

原 HTTP runner 的随机 `/tmp` 可执行文件路径会不断引入新程序身份。现改为项目生成路径 `campus-pet/build/health-transport-tests/HealthProbe`：先在同目录临时编译，再原子替换到稳定路径，编译失败保留原宿主，不执行旧产物冒充本次编译。此改动只稳定测试宿主路径，不修改 LuLu 或扩大代码中的允许端点；用户以后恢复逐程序审批时，仍可针对这个固定路径作决定。不能将旧开发预览规则视为新版本自动获准。

## 本轮代码边界

- `LocalHealthTransport` 只允许 `http://127.0.0.1:<1024..65535>/api/healthz`，拒绝用户名/密码、查询、fragment、其他主机/协议/路径。现有生产/隔离端口选择规则保持原样；测试永不连接 5173。
- 每次探测使用独立 ephemeral 会话，禁用代理、URL cache、cookie 和凭据存储；发送 `Connection: close`，拒绝全部 HTTP 重定向。没有第二套 shutdown 或用户会话通道。
- `verifyHealth()` 保留单次 3 秒期限，不增加重试；停服确认保留原单次 1 秒和总期限/连续两次连接拒绝语义。原始 `URLError` 继续抛出。
- 原身份 `application=campus-companion / mode=local`、非 200 拒绝及已有能力检查保留；新增必须能力 `project-completion-v1`，旧 2.4.7/2.4.8 后台缺该能力时拒绝复用。
- 最多保留 64 次安全诊断：随机 probe ID、端口、耗时、HTTP 状态、NSError domain/code、URLSession transaction 阶段布尔值、是否复用/代理、来源类型。没有响应正文、cookie、资料路径、环境、Key 或模型输入。
- 实际 smoke 成功或失败都会写出 `health-diagnostics.json`，包括启动、取消 sheet 后检查以及停服确认。该文件应随实际验收日志保留。

Apple 的 [transaction metrics 文档](https://developer.apple.com/documentation/foundation/urlsessiontasktransactionmetrics/fetchstartdate?language=objc) 定义了 fetch/connect/request/response 时间边界；[waitsForConnectivity 文档](https://developer.apple.com/documentation/foundation/urlsessionconfiguration/waitsforconnectivity?language=objc) 说明其只影响建立连接阶段。本轮依据实际 metrics 定位边界，没有从缺少后台日志反推唯一根因。

## 验证状态与重跑

新能力用例先失败（旧实现接受缺失 `project-completion-v1`），加入门槛后原生逻辑检查通过。受控共享旧连接探针先稳定超时，独立会话探针对照通过。身份、非 200、每项能力缺失与静态 loopback 拒绝由 `NativeTests.swift` 执行。

```sh
backend/.venv/bin/python campus-pet/tests/run_native_tests.py
backend/.venv/bin/python campus-pet/tests/run_health_transport_tests.py
```

第二条包含 10 个隔离 HTTP 场景：原点拒绝、旧连接、cache/cookie、错误身份/模式/新能力、非 200、坏 JSON、重定向与 3 秒超时。设置前九个联网场景失败，仅原点拒绝通过；用户授权修改模式后 10 项完整通过。runner 对负面身份场景要求真实 HTTP 返回，超时场景要求服务器确实收到一次请求，因而不会把“根本没连出去”误当拒绝/超时验证成功。测试无探索性绝对路径依赖，不进行内部重跑。

最终实际 App 仍由主代理统一重跑并读取 metrics：若仍出现 before-connect 停滞，继续检查该实际路径的规则匹配和系统访问边界；若通过，记录为本次完整联调通过，并保留设置前失败证据。历史间歇失败没有逐请求防火墙证据，不能一概归为同一原因。

## 实际App最终复核

当前源码重新构建的App在LuLu设置调整后完成完整原生联调（passed=true、56项检查、exit0），包含取消停止sheet后的两次独立health与认证停服；结果和metrics保存在 `docs/validation/demo2.4.9/native-current-result.json`、`native-current-health-diagnostics.json`。另一次预发布验收发现审批对话异步恢复时，测试过早点击尚未显示的批准按钮；保留失败结果/截图后，验收改为等待真正可用按钮，同源重建后通过。这是测试就绪条件修正，没有跳过业务断言。正式发布再次从源码重建与独立复验。
