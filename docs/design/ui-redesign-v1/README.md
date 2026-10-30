# 课间新界面 · 设计稿 v1

直接打开 [index.html](index.html)，或在预览服务运行时访问 [可点击预览](http://127.0.0.1:5349/)。右上角可切换 App 主窗口/快捷面板。

这是独立设计原型，使用合成示例数据；没有接入正式应用或真实API，刷新会重置交互。未改正式应用版本。

## 使用形态

正式产品只使用独立App，浏览器仅用于学校课表导入时本人登录。导入结果回到App校对确认；图片/PDF/文字导入也在App内完成。当前网页仅为开发预览，正式版本将移除日常网页版入口。

## 内容

- 四个主入口：今日、日程、任务、助手；设置放在底部。
- 目标、复盘归入任务；课表和学习安排归入日程，通过筛选区分。
- 复杂操作统一在详情面板展开，常驻页面不铺长说明和表单。
- 可试用：页面切换、任务搜索/添加、详情、安排预览和确认、计时和记录、示例导入、课程规则面板。

[完整设计说明](../../superpowers/specs/2026-10-30-ui-redesign-design.md)记录功能归位、视觉、原接口保留要求和待审阅范围。独立设计可实施性检查没有发现必须追加的问题。

浏览器检查结果见 [preview-verification.json](preview-verification.json)：五个主页面、主要原型交互、390px/320px内容宽度检查通过；截图在 [screens/](screens/)。这仅为设计原型验证。

图标使用项目已有的lucide-react，许可证见 [LICENSE-lucide.txt](LICENSE-lucide.txt)。无外部字体或CDN依赖。

## 后续实现计划

用户已要求将NaiWaChatPet形象替换纳入同轮实施。见[App新界面与桌宠总计划](../../superpowers/plans/2026-10-30-app-ui-implementation.md)、[桌宠形象替换详细计划](../../superpowers/plans/2026-10-30-naiwa-pet-assets-implementation.md)及[素材调研快照](naiwa-asset-research.json)。当前原型与正式桌宠资源尚未替换。
