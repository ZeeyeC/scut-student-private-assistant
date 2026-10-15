# 华工课表扩展安装与实测边界

A方案桌面版已附带预构建扩展。点击“导入华工课表”会弹出安装/检测/开页/校对向导，使用“打开扩展文件夹”加载稳定目录；无需用户下载JSON或手工复制课表。详见 [桌面说明](desktop.md)。下方构建命令供源码开发与共享站点使用。


## 构建并加载

先 `npm --prefix extension ci`。开发助手 origin 为 http://127.0.0.1:5173。

macOS（项目根目录）：

```sh
cd extension
PUBLIC_ORIGIN=http://127.0.0.1:5173 SCUT_ADAPTER_PATH=../config/scut-undergraduate-2026-10-14.json npm run build
```

Windows PowerShell（项目根目录）：

```powershell
$env:PUBLIC_ORIGIN = 'http://127.0.0.1:5173'
$env:SCUT_ADAPTER_PATH = '../config/scut-undergraduate-2026-10-14.json'
Push-Location extension
npm run build
Pop-Location
Remove-Item Env:SCUT_ADAPTER_PATH
Remove-Item Env:PUBLIC_ORIGIN
```

Chrome 打开 `chrome://extensions`，Edge 打开 `edge://extensions`，启用开发者模式，加载已解压扩展目录 `extension/.output/chrome-mv3`。这是本项目本机构建的扩展，未发布扩展商店。更新构建后点击重新加载扩展，并刷新助手和学校页。

## 用户流程

1. 助手“课表”点击“导入华工课表”，或对 Agent 说“帮我导入课表”。GUI 联系本机扩展。
2. 扩展打开、聚焦固定华工主入口 `http://xsjw2018.jw.scut.edu.cn/`。只有扩展真正回执才显示“教务已打开”。
3. 本人完成学校登录和验证码，按学校菜单找到“个人课表”，选择学年、学期并点击“查询”。应用持续提示这一步。教务菜单新开的课表标签页会通过浏览器 opener 关联到本次导入，请保留入口页直到出现预览；手工另开的无关页面不会自动关联。
4. 扩展等待查询后课表 DOM 变化、学期一致和稳定加载，自动读取已选课程。无需导出 JSON、复制页面或上传课表文件。
5. 回到助手校对课程、周次、节次、地点与变更；点击准备保存，再确认保存。只有事务成功显示“已保存”。可取消；会话 15 分钟过期。

GUI 刷新会恢复现有扩展会话，MV3 worker 重启从 storage.session 恢复，不重复开学校页。关闭浏览器会终止 session storage，重新发起导入即可；不会沿用旧 session。扩展只有助手精确 origin 与学校精确 origin 权限，以及 storage/alarms，不申请 all_urls、cookies、debugger、webRequest。

## 已实测结构（2026-10-14 本人登录后）

本人后续确认该学期第1周周一为2026-08-31；在助手“设置”中保存此日期，周数至少覆盖实测课程的第22周。各节次开始、结束钟点仍待校对，不用推测时间替代。

主入口本人提供并打开；登录后的个人课表路由为 `/jwglxt/kbcx/xskbcx_cxXskbcxIndex.html?gnmkdm=N2151&layout=default`。该独立页未发现 iframe。本次学期选择是 2026–2027 学年第 1 学期，共 23 条已选课程安排；不能据此承诺研究生或其他学校布局。

- 学年、学期选择器 `#xnm`、`#xqm`；查询按钮 `#search_go`。学期选项的 value 不等于显示的 1/2，按选项文本核对。
- 可见网格 `#kbgrid_table_0`、列表 `#kblist_table`。选择列表而非其他实验 jqgrid；可见网格加载后可读取同一课表的隐藏列表。
- 星期由 `xq_rowspan_1…7`；节次由 `jc_星期-起节-止节` 的 rowspan 上下文；课程在 `.timetable_con`。只取 `.title font[color=blue]` 已选课程，排除红色待筛选条目。
- 只规范化课程名称、周数、节次、地点、教师、校区和教学班标识，再由 DOMPurify 清理为平面表，后端 lxml 验证并 pandas.read_html 解析。不复制课表标题中的姓名、学号、教学班组成或整页。
- 实测周数包含“第13周”、分段单双周和“1-16周,21-22周”，均有测试。节次为 1–12，页面未提供对应钟点；开学周一、学期周数与钟点须本人校对。

本次未取得分页、过滤无遗漏的每次捕获证明，所以草稿 completeness=partial；未出现的旧课程保留并提示，不能自动删除。不同学期课程共存在当前课程集合内；导入另一学期前需校对已有课程和开学设置，目前不提供按学期归档切换。

## 尚待真实验收

实测 DOM 发生于 Codex 内置浏览器，内置浏览器不是目标 Chrome/Edge 的扩展运行环境。专用布局的 Chromium 自动化测试使用明确虚构课程，证明自动提取和 worker 恢复机制，不构成真实学校扩展验收。仍需用户在 Windows/macOS Chrome/Edge 加载扩展，用真实学校页走完整预览、确认流程。没有读取学校密码、cookie 或验证码。
