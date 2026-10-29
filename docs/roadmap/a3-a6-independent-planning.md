# 甲独立规划核心交付（Demo2.4.7源码候选）

按用户“基本功能完整、接口清楚，先跳过乙协作”的要求，本阶段交付甲可独立实现的规划功能；不表示原任务书全部细节或乙联调已完成。

## 使用与范围

- A1课程分段、A2统一冲突、A3重复硬禁排/容量沿用现有实现。
- A3新增软偏好：沿用「禁排时段」编辑器，选择“软偏好（优先学习，可让步）”，支持单次、每周、有效期、修改及停用。软偏好不占用日历，不从容量中扣除；硬禁排始终必须避开。
- A3/T06方案比较：「比较安排，再做决定」提供“更早开始”和“遵循软偏好”。两者共用课程、硬约束、截止、依赖、预算和步骤数据，展示可排/未排及偏好匹配分钟；未设置偏好时允许方案相同。当前偏好策略在同一天内优先使用已确认窗口，随后使用其他空档；如果偏好切分导致少排工作，则让步回退至可排工作量更大的较早方案，不宣称全局最优。选择只生成原计划草稿，确认后保存；每个新时间块说明偏好使用或让步原因。
- A4沿用局部重排，继续保护锁定、完成、已开始和范围外事实。乙执行事件、权威汇总、更正尚未接入。
- A5/T05作息候选：按这次明确填写的每日作息、课前准备、课后复习分钟生成未来7天候选；跨校区转移仅使用设置中已确认的方向性分钟。缺作息或校区/时长则提示缺失，不推测课程类型、早餐/午休或个人习惯。当前规则是一次请求参数，非乙个人档案，不保存另一套用户模型。可重复预览，忽略操作持久化；同一候选保持已忽略状态，不自动添加。接受后先生成固定事项草稿，沿用核对冲突与确认流程。过去或冲突候选禁止接受，重复已加入的事项也会显示冲突。
- A6/T14/T15甲端计算：只读的容量、截止/未排风险及双方案供乙主动建议和协商调用，不写乙的触发、频控、稍后处理、安静时段或协商存储。未知耗时与已逾期分别标识，不把缺记录当成0实际投入。

T09按已知每日学习上限和硬占用减负的基础计算可用；精力/目标/执行数据驱动的个性化排序需乙接口，当前不伪造。学校校历/实践周的详细规则和真实OCR样本指标仍待资料与后续专项验收，本阶段不细化批量操作。

## 精确接口

保留既有认证、CSRF、Idempotency-Key、资源revision、全局source_revision和草稿确认。

1. `POST /api/drafts/scheduling-constraint`：原`constraint`新增`strength:"soft"`，默认`hard`兼容旧数据。软规则预览返回发生窗口，`affected_plans`为空，不冒充冲突。
2. `GET /api/planning-options?target_date=YYYY-MM-DD&horizon_days=7`：只读`Options`，同一份输入计算两个方案。每个`Option.id`为`earliest|preferred`，含预览块、`proposed_minutes`、`unallocated_minutes`、本范围未完成安排的`preferred_minutes`、变更数量和解释。
3. `POST /api/plan-drafts`：在原请求上添加`strategy:"earliest"|"preferred"`及可选`expected_source_revision`；版本不匹配409，返回原计划草稿。`POST /api/replan-drafts`也接受这两个字段，保留有效安排而只对新增分配应用偏好。选择后的草稿仍需校对确认。
4. `GET /api/planning-risks?target_date=...&horizon_days=7`：只读`Risks`；`risks[].code`为`unknown_estimate|overdue|unallocated`，带任务/步骤引用、未知或剩余分钟和程序原因。无后台提醒或自动接受。
5. `POST /api/daily-routine-preview`：`{confirmed:true,target_date?,horizon_days:7,daily_windows:[{title,start:"12:00",end:"12:30",weekdays:[1,2,3,4,5]}],preparation_minutes:15,review_minutes:20,include_campus_transfer:true}`。所有规则由调用者明确指定；空规则仅返回缺信息提示。只读候选含稳定ID、真实起止、冲突、是否忽略和`can_add`。
6. `POST /api/daily-routine-drafts`和`POST /api/daily-routine-dismiss`：请求均为`{candidate_id,expected_source_revision,request:<上述预览请求>}`，写入需原幂等键。前者重算并校验候选，返回原`calendar_event`草稿；后者仅保存用户忽略记录，不影响规划资料版本。拒绝资料过期或不存在的候选，接受也拒绝冲突/已忽略/过去候选。

新增资源仅甲方的`routine_dismissal`，由既有全量导出、备份和清空资料机制管理，无新数据库表或依赖。规则版本为`soft-preferences-2`，旧规划草稿必须重新生成，防止用旧规则确认。当前`profile_integration`、`goal_integration`、`execution_integration`明确为`pending_person_b`，不是已存在的乙接口。

## 验证与边界

新增10项后端核心场景覆盖软偏好取舍、硬禁排/截止保护、重叠偏好不重复计分、有效期、未知/逾期、只读、确认/过期、作息无猜测、持久忽略/重启、接受/重复、课前课后冲突、方向通勤和跨用户。新增2条浏览器流程覆盖软偏好设置与方案校对保存、390px候选忽略/接受；连同上一轮A4的13项及2条流程实际执行。冻结服务增加方案/风险只读、选择确认、候选忽略与固定事项保存检查。完整结果以正式manifest或失败归档为准，不用合成资料声明真实OCR准确率。

未改乙agent.py/tasks.py/Chat.tsx/TaskDetail.tsx、档案、目标、原生桌宠或S02；公共前端既有挂载改动以Demo2.4.3源码为对照核验。需要乙提供的内容单列《乙方需提供的交接清单.md》。


## 最终发布状态

正式Demo2.4.6已通过完整发布检查并保留。2.4.7新增软偏好碎片回退与去重规则版本绑定，后端348项及18子测试、前端14项通过，浏览器33条通过；既有conflicts.spec固定事项过期预览场景在预期409提示后读取fixed-events超时，根因未定位。2.4.7不正式发布，不以独立冻结/原生复查替代该失败；候选源码可交乙接入，旧正式入口不变。未完成的真实乙接口与专项验收见交接清单。
