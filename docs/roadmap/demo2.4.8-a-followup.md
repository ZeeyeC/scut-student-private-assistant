# Demo2.4.8 · 甲方后续核心交付

基于乙方 `596b4d06ff8930661b46c1115cab78e1a71ad2f7`，本地分支 `integration/person-b-delivery-2.4.7`。采用乙的执行、计时、档案、目标、周复盘、助手及协商实现，不另建这些领域的存储或界面。本轮按用户“核心功能实现、接口清楚，不必精修全部细节”的要求完成后续任务单 A-01～A-05 的基础功能。

## 已实现

| 任务 | 实际行为 | 入口与验证 |
| --- | --- | --- |
| A-01 权威执行输入 | 每个任务/步骤直接调用乙 execution_summary，读取有效更正链和计时状态；替换 spent_minutes 投影，避免重复相加。实际、旧估算、未知、明确0分开。无步骤归属的投入单独报告，不猜扣某步骤 | planning_facts.load_facts → 普通排程、容量、风险、比较、协商、重排；60−25=35，更正后60−20=40 |
| A-01 事实保护 | 锁定、完成、已开始、范围外、运行/暂停/异常未结束计时的关联块保留，冲突另报；确认不会删除再创建原样保留的块 | planner.planning_result/build_plan/save_plan；旧草稿事实变化返回409 |
| A-02 事件闭环 | 活跃日程界面挂载、回到前台及每30秒合并消费既有 planning_event；启用的乙主动建议刷新也复用消费服务；任务/课程/设置等无显式事件的变化通过事实清单补一条既有 planning_event | /api/replanning/changes；每用户一份持久化 replan_notice，事件注明 planning_consumed/notice ID；GET与inactive不消费 |
| A-02 生命周期 | 同事实重复检查不写第二份建议；支持忽略、过期、关联原重排草稿和已确认状态。确认事件不自触发；计时心跳不当成新规划事实。新事实合并重新计算，确认前正式日程不变 | /changes/draft、/changes/dismiss；均沿用 owner、版本、事务、幂等回执及原 PlanReview |
| A-03 档案计算 | 已确认且在有效日期/档案时区内的通用学习时段、高低精力、专注/休息、每日负荷和休闲偏好参与排序或分块；复习间隔用于明确指定分钟的课程复习候选，包含前几日课程基准 | 偏好方案/日常候选；档案来源、版本、配置字段、支持字段及缺口可查；重置后不残留偏好 |
| A-04 目标分配 | 在同一套空档中分配已关联的真实任务。目标优先级/期限/周预算参与；重复关联只归一个活动目标，暂停不产生目标驱动安排。返回逐目标逐周已排、已知实际小计、预算缺口及许可 | planning-capacity/options/risks 的 goal_allocation；600预算、360共享容量实排360、缺240 |
| A-04 调整许可 | reduce允许部分分配；delay仅在既有期限和规划范围内延后；ask在不足时不新增部分安排，列出需要询问的未排工作。均不改任务/目标截止 | 既有任务即使所属目标暂停仍可独立排程；不会为填预算虚构任务 |
| A-05 时长生成 | 同一步骤至少3条可靠真实记录、末次完成反馈，按有效记录累计总量向上取5分钟；不是会话中位数或跨任务习惯学习。生成typed pending建议，接受/拒绝/恢复全部复用乙 | /duration-suggestions/generate；已有乙列表状态扩展为ready，页面“检查并生成时长建议” |

## 公共接口与兼容补丁

- 新增 `backend/app/planning_facts.py`、`planning_changes.py`、`duration_generator.py`；既有统一规划输入和规则版本升级为 `personal-facts-1`。旧规则草稿需重新生成，不修改正式事实。
- `CapacityReport` 增加 execution_context、profile_context、goal_allocation；`Options` 增加后两者；`Risks` 增加执行与目标依据。已有字段保留。统一 OpenAPI 与前端生成类型同步。
- `execution_context.steps[id]` 保留乙汇总原字段并补 records/timers；`tasks[id]` 另含 task_status/unassigned_record_ids。实际总量缺记录为null；known_actual_minutes只是已知小计，不能称为完整实际耗时。课程/已完成块分钟不补成实际分钟。
- `profile_integration=confirmed_profile_v1`、`goal_integration=goal_budget_v1`、`execution_integration=authoritative_execution_v1` 表示读取服务已接入，不表示用户已有档案或完整事实。
- 乙文件最小补丁：proactive.refresh_suggestions 调用同事务消费；duration_suggestions 列表/DTO状态兼容 `not_integrated|ready`，消费行为不改；DurationSuggestions 提供生成/重试按钮与真实空态；NegotiationPanel 等待 settings/intents/blocks 刷新结束，修复缓存旧版本的偶发409。其余执行、计时、档案、目标与助手存储保持乙实现。
- imports.commit_draft 为日常候选生成的 calendar_event 增加来源版本检查；普通独立事项仍保持原规则。新档案或课程事实变化后，旧候选不能按过期依据保存。
- 新 Resource 仅 replan_notice 和符合乙v1的 duration_suggestion，复用现表，无SQL迁移。事件追加 planning_consumed/planning_notice_id，不影响乙的读取。源码回滚可忽略replan_notice；生成建议仍能由乙原消费器读取。含新版规则的未确认计划必须重建。

### 请求与失败示例（合成）

```json
POST /api/replanning/changes
{"app_active": true}
// {"consumed":2,"notice":{"id":"…","kind":"replan_notice","revision":1,"data":{"state":"pending","source_revision":12,"report":{},"event_ids":["…"],"draft_id":null}}}

POST /api/replanning/changes/draft  （Idempotency-Key必填）
{"revision":1,"source_revision":12}
// 返回原plan草稿；随后使用既有 /api/drafts/{id}/confirm。

POST /api/replanning/changes/dismiss （Idempotency-Key必填）
{"revision":1,"source_revision":12}

POST /api/duration-suggestions/generate （Idempotency-Key必填）
{"expected_source_revision":12}
// {"rule":"same-step-observed-total-1","created_ids":["…"],"refreshed_ids":[],"skipped":[],"result":{"generation_status":"ready","suggestions":[]}}
```

示例省略建议/报告细节，准确结构见 OpenAPI；data 中报告为真实计算结果。新操作版本不符409、缺Key422、跨owner资源404/本人的空集合；精确重试先返回历史回执，不重复应用。自动消费是按事实指纹进行的幂等合并操作，没有第二套保存计划的入口。

## 耗时建议规则与边界

1. 同任务同一步骤、3～1000条有效更正链尾、source为manual/timer、每条正整数分钟、feedback为partial/completed，逻辑末次为completed。更正沿原执行顺序，不因补写更正改变末次会话顺序。
2. 未确认计时区间、旧估算、0/未知/跳过/未开始不能充作可靠样本。总量超出5～240分钟不截断，明确提示人工拆分。保留每条execution ID、revision、actual_minutes和feedback。
3. 对这一步骤的已观测总量建议新的总预计，不推断下一任务、长期习惯或实际已完成任务状态。只记录候选；接受只改正确步骤的预计值，仍以乙的版本/回执/恢复保护执行。
4. 身份由owner、规则、步骤、样本依据确定，无关事实变化不复活拒绝/接受/恢复后的建议。尚待确认且原预计未被改动时可重新核对版本，旧revision的操作409。新执行或更正构成新依据，旧建议由乙标过期。

## 仍未完成，交接时必须保留的缺口

| 内容 | 需要什么/当前边界 |
| --- | --- |
| 真实华工OCR准确率验收 | 用户/学校匿名真实课表至少30份、5种布局及人工标注；当前自动化为隔离合成数据，不声明95% |
| 实践周、校历顺延、批量调课及撤销专项 | 仍需用户/学校确认校历和具体批量规则；保留既有单双周、显式周次、单次调课/停课/恢复；不猜补课日。批量事务界面与完整实践周流程未在本轮实现 |
| deep/review类型偏好、按课程类型推准备时长 | 任务/课程缺已确认的类型与难度字段及规则，需要双方约定；目前明确报告缺口，显式准备/复习分钟继续可用 |
| 更细评分与个性化效果 | 当前为可复现截止/优先级/预算/偏好启发式，不是全局最优；精细目标负荷权重、跨任务耗时泛化、周复盘自由文字转条件未实现 |
| 跨周/跨时区真实投入 | 有效记录只含当地日期时，其可能区间跨规划周就不猜归属；goal报告actual_total_known保守为false，小计不代表整周完整投入 |
| 真实体验与设备验收 | 跨校区实际耗时、用户执行和协商效果，Intel Mac/Windows需对应数据/设备；本轮为Apple Silicon本地验证 |
| 原生偶发健康请求超时 | 遵循既有流程：仅明确超时允许一次保留证据后的重跑；不声称本轮修复根因 |

乙现在无需再提供执行/档案/目标接口，已有真实领域已接通。后续需要乙配合的是类型字段升级、真实使用反馈及上述专项联调，而非重新交付既有代码。

## 验证与交付

新增 `backend/tests/test_person_a_delivery.py` 覆盖实际/未知/0/旧估算、更正、任务状态、无归属投入、跨时区档案、休息/负荷/0、复习间隔/重置过期、目标共享/去重/暂停/ask/期限、事件去重/确认/忽略/重启/回滚、时长生成/版本/采纳/拒绝/恢复/owner/回滚。浏览器新增4条真实前后端操作，包括协商刷新竞争的确定性门禁。实际冻结包沿既有A+B检查新增8条行为检查。

完整后端/脚本、前端、浏览器、原生、冻结包与签名/隐私/ZIP结果以正式包中的验证结果、日志、manifest及SHA256为准；开发阶段失败日志保留，不将未运行的验证写为通过。不调用付费模型，不推送GitHub/PR，不录屏。所有已有正式版本及Demo2.2、旧失败暂存、配置和个人数据保留。

首轮整包检查：后端574项及20子断言、前端82项通过，浏览器51通过/2失败，完整保留在工作区 `.Demo2.4.8-staging-attempt1-20261030`（含trace和失败记录）。已定位并修正测试：课后询问初始化完成后再设置测试课表，避免自动打开弹窗遮挡手动打开按钮；容量直接GET仍全量资源不变，进入页面的事件消费只允许更新notice/event，所有业务事实仍逐项一致。对应8条流程已通过后重新执行完整发布，最终结论以正式归档为准。另补跨午夜休息预留回归；甲方新增26项针对性测试通过，旧候选冻结服务的25项甲乙行为预检通过，不替代最终App验收。

第二轮整包：后端575项及20子断言、前端82项、浏览器53条、原生逻辑及原生App56项通过，停在冻结课表检查中旧规则字符串断言。第二轮App/日志/原生证据保存在 `.Demo2.4.8-staging-attempt2-20261030`；修正断言后同一实际冻结服务的PDF/课表/规划16项预检通过。再次完整发布前补齐偏好安排前后及跨日期的休息预留，相关26项甲方回归通过；不是跳过冻结检查后发布。
