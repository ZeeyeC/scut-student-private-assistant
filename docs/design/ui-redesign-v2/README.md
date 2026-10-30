# 完整窗口与桌宠待办 · 视觉修订 v2

2026-10-30。状态：**设计提案，继续收集用户意见；没有修改正式App，也没有发布新版本。**

直接打开[index.html](index.html)。上方可切换“完整窗口 / 桌宠待办”；App左导航可查看今日、日程、任务、助手、设置。日程的“导入课表”默认展示学校浏览器导入，下方是图片/PDF、文字两种折叠方法。桌宠默认只有角色，单击才出现方形待办窗口；任务详情在同一个窗口内切换。

完整窗口依据[v1最初设计](../ui-redesign-v1/index.html)恢复比例与留白。全部操作都是合成示例，不访问生产API、不打开外部浏览器、不上传文件、不调用模型。参考中的“示例回传/解析”等按钮仅供查看状态排版，正式产品不包含这些演示按钮。设计预览使用浏览器技术，不改变正式产品只使用独立App的约定。

- [完整设计规格](../../superpowers/specs/2026-10-30-ui-refinement-design.md)
- [新修改计划及用户意见记录](../../superpowers/plans/2026-10-30-ui-refinement-implementation.md)
- [颜色、字级、尺寸及验收参数](visual-contract.json)
- [参考文件与截图SHA256](reference-manifest.json)
- [设计原型检查结果](preview-verification.json)
- [一次独立可实施性复核及处理](builder-check.md)
- [持续进度](../../roadmap/Demo2.5-开发进度追踪表.md)

## 对照截图

| 状态 | 参考 |
| --- | --- |
| 今日完整窗口 | [today-desktop.png](screens/today-desktop.png) |
| 日程 | [calendar-desktop.png](screens/calendar-desktop.png) |
| 任务 / 详情 | [tasks-desktop.png](screens/tasks-desktop.png)、[task-detail.png](screens/task-detail.png) |
| 助手 / 设置 | [assistant-desktop.png](screens/assistant-desktop.png)、[settings-desktop.png](screens/settings-desktop.png) |
| 默认导入 / 窄窗口 | [import-default.png](screens/import-default.png)、[import-compact.png](screens/import-compact.png) |
| 桌宠收起 / 列表 / 详情 | [pet-idle.png](screens/pet-idle.png)、[pet-todos.png](screens/pet-todos.png)、[pet-detail.png](screens/pet-detail.png) |
| 随系统深色参考 | [today-dark.png](screens/today-dark.png) |

完整窗口参考外框1280×820，其中38为示意标题栏，**固定产品内容为1280×782**；原型检查的截图不包含预览工具控件。正式App按实际系统标题栏补足外框，视觉对照只比较1280×782产品区，保留全部产品内容。其他宽度属于自适应检查，不能缩放整张1280截图伪装窄屏适配。

## 检查与复用

在项目根目录使用已安装依赖运行：

```sh
node docs/design/ui-redesign-v2/verify-reference.mjs
```

脚本使用隔离的无头Chrome，检查五页、内容滚动时导航不动、默认导入层级、桌宠默认隐藏/单击展开、任务定位，以及1280/1024/960/768/560/390/320宽无横向溢出。只验证本原型；不能用它代替正式App或真实学校验收。准备时检查脚本曾因同名动作按钮定位不唯一而停止，已改用可访问名称并完整重跑；最终结果以JSON为准。

后续实现以用户最终接受的参考hash为准。不能把实现截图反向覆盖设计基准使检查通过；需要设计变更先记录用户意见并同步规格/原型。当前manifest状态不是accepted。

## 素材

角色直接使用项目现有NaiWa原PNG，未重绘、变色或替换：源文件及许可依据见[campus-pet/art/naiwa/SOURCES.md](../../../campus-pet/art/naiwa/SOURCES.md)、原包的[LICENSE](../../../campus-pet/Resources/NaiWa/licenses/source-0.txt)与[NOTICE](../../../campus-pet/Resources/NaiWa/licenses/source-1.txt)。独立角色许可未另外核实的记录保持原样。

原型图标由预览运行时的Lucide提供，项目原设计的[Lucide许可](../ui-redesign-v1/LICENSE-lucide.txt)保留。预览的运行时图标辅助可能需要允许的静态资源；不连接任何业务服务。参考正文、样式、交互和角色图在本地文件内。
