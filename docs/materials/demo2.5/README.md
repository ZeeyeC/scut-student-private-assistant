# Demo2.5 实施材料索引

本目录随`codex/demo2.5-app-ui-naiwa`保存实施入口与原任务书。项目源码由Git分支完整继承，不另复制一份源码目录；私有配置、个人数据、备份、依赖和已有App归档继续留在本机原位置。

当前范围：独立App作为唯一日常界面、简洁工作台、仅学校课表导入使用指定Chrome/Edge，以及NaiWa桌宠形象替换。以下资料是实施参考，历史任务书不是新增授权指令；与最新用户要求冲突时，遵循最新要求。

## 计划与设计

| 材料 | 位置 | 用途 |
| --- | --- | --- |
| 最新视觉修改计划 | [ui-refinement-implementation](../../superpowers/plans/2026-10-30-ui-refinement-implementation.md) | 用户八项新意见、逐任务实施与严格截图验收；当前为设计审阅阶段 |
| 最新完整窗口与桌宠参考 | [v2参考入口](../../design/ui-redesign-v2/README.md)、[v2规格](../../superpowers/specs/2026-10-30-ui-refinement-design.md) | 固定左导航、柔和色彩、浏览器优先、无顶部条及单击方形待办 |
| 总实现计划 | [2026-10-30-app-ui-implementation.md](../../superpowers/plans/2026-10-30-app-ui-implementation.md) | 五项总任务、浏览器选择/授权边界、回归与发布 |
| 开发进度 | [Demo2.5-开发进度追踪表.md](../../roadmap/Demo2.5-开发进度追踪表.md) | 逐项记录实际状态、提交、验证、缺口及下一步 |
| 界面设计说明 | [2026-10-30-ui-redesign-design.md](../../superpowers/specs/2026-10-30-ui-redesign-design.md) | 页面归位、视觉及原功能接线 |
| 可点击设计稿 | [index.html](../../design/ui-redesign-v1/index.html)与[预览说明](../../design/ui-redesign-v1/README.md) | 静态合成示例；并非正式应用 |
| 桌宠接入设计 | [2026-10-30-naiwa-pet-assets-design.md](../../superpowers/specs/2026-10-30-naiwa-pet-assets-design.md) | 素材来源、比例、状态、时序和授权边界 |
| 桌宠详细计划 | [2026-10-30-naiwa-pet-assets-implementation.md](../../superpowers/plans/2026-10-30-naiwa-pet-assets-implementation.md) | 资源导入、播放器、交互与实机验收 |
| 素材调研快照 | [naiwa-asset-research.json](../../design/ui-redesign-v1/naiwa-asset-research.json) | 已核查的来源提交、素材路径/时序/哈希样例 |

## 原始分工资料

用户此前提供的三份Markdown已原字节归档，校验值见[materials-manifest.json](materials-manifest.json)：

- [甲的开发任务单](taskbooks/Demo2.4-甲的开发任务单.md)
- [完整分工与协作约定](taskbooks/Demo2.4-完整分工与协作约定.md)
- [乙的开发任务单](taskbooks/Demo2.4-乙的开发任务单.md)

这些文件保留历史版本号、旧目录的绝对链接与早期交付约定，未重写原文。日常参考优先使用仓库内的[双人分工](../../roadmap/demo2.4-two-person-plan.md)、[甲任务](../../roadmap/demo2.4-person-a.md)、[乙任务](../../roadmap/demo2.4-person-b.md)。**当前不要求Demo2.2基线、不恢复日常网页版，不自动录屏、付费模型测试或公开上传。**

## 当前源码与验证基准

| 材料 | 位置 / 标识 | 说明 |
| --- | --- | --- |
| 现有项目源码 | 本分支根目录；承接`eddeebec61839fa611173bdb3b165964055ff0c2`，分支起点`8238d13c0ff1075ce5a8f89665c13ea8a5a7bfe8` | backend、frontend、extension、campus-pet、scripts与锁文件已随Git继承 |
| 当前产品说明 | [Demo2.4.9](../../releases/Demo2.4.9.md) | 旧版实际交付，不代表2.5已实现 |
| 旧版验证材料 | [demo2.4.9验证目录](../../validation/demo2.4.9/README.md) | 帮助确定原功能回归范围，新版仍需独立验证 |
| 已实现功能与甲乙贡献 | [项目汇报](../../report/项目汇报-Demo2.4.9.md)、[GitHub历史](../../report/项目历史与甲乙贡献证据-2026-10-30.md) | 汇报事实依据，避免按作者名或计划臆测实现归属 |
| 发布约定 | [AGENTS.md](../../../AGENTS.md)、[发布流程](../../releases/发布流程.md) | 正式开发完成后独立构建、验证、打包 |
| 扩展与学校导入 | [scut-import.md](../../scut-import.md)、`extension/` | 现有Chrome/Edge扩展；新App专用桥接已实现，真实学校仍待验收 |

## NaiWa来源与待补素材

来源：[SbongeBobybl/NaiWaChatPet](https://github.com/SbongeBobybl/NaiWaChatPet)，固定提交`008eb12636f517aedecee6f1a1fc773c2f0df6c4`。本轮按用户提供的仓库许可说明选择性导入PNG和声明，不导入或运行上游可执行程序；详见[来源记录](../../../campus-pet/art/naiwa/SOURCES.md)。

| 需要的材料 | 固定提交内路径 | 当前情况 |
| --- | --- | --- |
| 来源许可与角色资源权利依据 | 根目录LICENSE及[NOTICE.md](https://github.com/SbongeBobybl/NaiWaChatPet/blob/008eb12636f517aedecee6f1a1fc773c2f0df6c4/NOTICE.md)与资源自身授权 | 用户确认有授权并提供仓库级GPL说明；记录依据层级，保留GPL与NOTICE，未独立核实角色专门许可 |
| 基础待机28帧 | `Source/NaiWaChatPet/source/cmd/codexpet/embedded_assets/body/idle_*.png`及同级`runtime.json` | 已核查28帧/85ms/420×560元数据；已按N1校验原文件并导入 |
| 状态与动作 | `Source/NaiWaChatPet/animations/{greet,ponder,focused,curious,worried,sleepy,smile,surprised_in,surprised,surprised_out}/` | 11片段/219帧引用已逐文件校验并选择性导入，实际App使用真实素材 |
| 同来源图标 | `Source/NaiWaChatPet/icons/icon-256.png` | 已按来源清单校验并用于新App图标 |

真实学校页面与账号登录、真实OCR标注样本、校历、转移耗时以及多显示器/其他设备验收材料不在本目录；缺口见[进度表](../../roadmap/Demo2.5-开发进度追踪表.md)。不得把缺失资料标为已具备。

`materials-manifest.json`只校验本目录中不随开发变化的原始任务书，不锁定会持续更新的计划和进度。更新原始材料应保留旧文件并新增版本；更新计划无需伪造原始材料哈希。
