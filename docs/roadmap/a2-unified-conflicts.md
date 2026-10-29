# 甲 A2：统一课表冲突与跨校区检查

在 Demo2.4.1 的实际占用分段基础上，完成 T03 的课程/固定事项时间检查与方向性校区转移检查，计划发布 Demo2.4.2。用户已要求甲优先做核心功能，本轮不扩展乙的用户档案、执行计时等模块。

## 使用与约定

- 课表中点「设置校区转移时间」，按方向填写两个校区及本人确认的分钟数。A→B 不代表 B→A。未填写方向、课程缺校区或前序课程重叠时显示待补充，不报告“赶得上”。同校区不同教室间的步行耗时尚不推断。
- 手工/空白格、教务网页、图片/PDF、文字课表及固定事项共用 `POST /api/drafts/{id}/conflict-preview`，请求与 DraftEdit 相同。课程调整也在最后确认前重算。全部为程序规则，不额外调用模型。
- 预览模拟真正保存后的课程集合：手工及网页 source_key 更新、已验证全量捕获才删除缺项；图片和文字按完全相同事实去重并保留旧课；调课替换所选原日期整次课程，停课移除本次。实际占用组参与检查，非连续节次空档不误判，连堂保护休息算占用，起止相接不算重叠。
- 一次保存前显示全学期内与本草稿有关的问题，包含已知调课日期。课表/待办日历显示当前日期范围内所有固定课程与固定事项的问题。嵌套长事项逐一列出，前10条后可展开余项。
- 规则检查可提示已确认的固定事实冲突，不会自动改课。界面有冲突或钟点配置不足时要求勾选知悉，再明确保存。缺学期锚点/节次时显示检查不完整，可保留已确认事实，补齐配置再核对，不宣称无冲突。

## 接口交接

新增 `StudentSettings.campus_transfers: [{from_campus,to_campus,minutes}]`，默认空，分钟为1..360整数，禁止空校区、同校区或重复方向。复用原 settings 版本、鉴权、幂等、导出及本地配置，不新增数据库表或Key入口。旧设置缺字段按空矩阵处理。

`backend/app/conflicts.py` 的 `detect_conflicts(events, settings, focus=None)` 是公共纯函数，输入实际 occupied course runs 与 fixed_event，排除 plan_block 和禁排；返回 rule_version、issues、conflict_count、pending_count。问题包含两边课程/事项原始时间证据；跨校区不足另有 required_minutes、available_minutes、shortfall_minutes 和 user_confirmed 依据。使用时刻比较，按用户时区判断是否同一天；不将不同夜晚直接相连。遇到重叠簇后续转移标记待补充。

草稿预览额外返回 complete、configuration_warnings、timezone、conflict_token。token绑定用户、草稿ID、规范化载荷、规则版本，以及 settings/课程/例外/固定事项版本。界面修改载荷后必须重查；确认请求携带 token，后端事务中重新计算，过期409、无部分写入。编辑草稿造成的 revision 增长不会单独使同一载荷token失效。确认回执保存 conflict_report 和 conflict_reviewed，支持重启与幂等重试。为兼容旧版客户端，原 revision-only 确认仍可保存已确认固定事实，同时返回 conflict_reviewed=false 和实时检查结果；新版界面始终使用token。课表替换/课程调整原有全局source_revision保护保留，资料过期须重新生成草稿。

canonical occurrence / ScheduleEvent 新增 campus。课程调整可明确填写本次校区；只收到新教室、没有确认校区时保持未知，不从教室字符串猜校区。旧版已调整记录未填campus且地点变化同样按未知；原课及恢复原课保留课程校区。

## 验证与后续

新增合成后端场景和浏览器桌面/手机流程覆盖间隔40/10、刚好40、方向未知、校区未知、半开区间、时区偏移、嵌套冲突、分段空档、保护休息、三种录入、固定事项、调课、预览版本/载荷过期、鉴权和持久化。发布时还在实际冻结后端校验新模块、只读预览、保存回执和日历报告。最终结果以版本目录日志和manifest为准。

本轮不生成通勤日程块，也不把转移矩阵当作已扣除的学习容量。下一步 T04/T05 将已确认的通勤/重复硬约束作为真实占用传入排程。学校校历、实践周、真实华工OCR样本准确率、自动重排等仍未完成。原有提醒、快捷方式、任务环、作业询问继续回归。

## 本轮开发粒度与协作交接

2026-10-28用户追加要求：具体功能不必过细，以功能完整为主，同时遵守协作协议。后续甲按最小完整闭环推进T04、T11等缺项，不以边缘体验精修拖延主流程，也不代做乙的T07/T08/T10/T12–T15。

本轮新服务和界面分别集中在 `conflicts.py`、`ConflictReview.tsx`、`ReviewedDraftActions.tsx`。保留 `Assignments.tsx` 原有 `DraftActions` 导出名，仅导入/再导出独立保存控件，任务/执行业务不变，避免将冲突算法塞入乙的任务模块；现有调用方无需改接口。未改乙统筹的 App.tsx、Settings.tsx、DraftReview.tsx、types.ts 或公共样式，本轮也没有修改乙的执行、档案、目标、助手工具及原生桌宠文件。Today.tsx已有A1的区间展示改动继续保留，本轮无新增改动。前端API文件由实际接口重新生成。乙可直接调用conflict-preview或消费calendar-events.conflict_report，不复制算法；后续公共挂载修改仍按总协作任务书交乙合入。

## 已知S02复现交接（乙负责）

第一次整包：后端294通过（另18子测试），浏览器25通过1失败。`timetable-text.spec.ts` 第一条补充周次后在第43行刷新，页面停在“正在连接助手…”，服务日志含请求取消及`sqlite3.OperationalError: no active connection`。当时尚未进行冲突预览，冲突新增4条浏览器流程已通过。完整失败材料保留于工作区`资料归档/Demo2.4.2-首次验证失败-20261028/browser.log`及`browser-test-results/`，含trace。此为已知S02复现，不在甲处修改agent.py/Chat.tsx等乙文件；后续整包复跑通过不能注销此问题。
