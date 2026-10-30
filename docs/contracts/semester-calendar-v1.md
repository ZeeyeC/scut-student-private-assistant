# 学期校历与批量调整 v1

实现模块：`backend/app/semester_contracts.py`、`semester_calendar.py`、`semester_routes.py`；界面：`frontend/src/SemesterCalendar.tsx`。

## 规则与边界

学校规则只能来自用户明确填写和确认。系统不内置公共节假日，也不会据此猜学校停课、顺延、补课、课程类型或实践周安排。课程仍保留原来的显式周次；校历规则以原 `exception` 记录作用于具体原课日期。

`practice_week` / `holiday` / `makeup` / `custom` 是用户选择的来源标签。它们不触发隐式算法。停课由明确日期范围和课程 ID 决定；补课由明确原日 → 目标日映射决定。一个原日只能有一个目标日，不同原日可以映射同一目标日，真实重叠会进入预览。

补课取原始课表该日的本地节次时钟和已知教室/校区，保留授课、课间和非连续占用分段；不会沿用之前单次调课的新教室或新时钟。若已有调整，预览同时显示当前实际状态与本规则确认后状态。单次特殊时钟或换教室继续使用已有单次课程调整入口。

一个批次最多200门课程、100行日期映射、500次课程；停课范围及每次补课位移不超过366天。某映射原日不存在所选课程时拒绝，不寻找“下一次课”。目标时刻在设置时区有夏令时缺失或重复时，拒绝猜测，提示先通过单次调课明确带时区的时间。没有学期第一周周一、节次时刻等配置时拒绝生成假预览。

## API

主注册：`semester_calendar_router(get_db, current_user)`；沿用现有登录、owner、CSRF、数据库事务和 `Idempotency-Key`。

- `POST /api/drafts/semester-calendar`：创建原 `draft`，`draft_kind=semester_calendar`。仅生成预览，不改变正式课表。相同幂等键和相同请求重放同一草稿，不同请求返回409。
- `GET /api/semester-calendars`：返回该用户的不可变批次 `ResourceView[]`。呈现层为原批次附加 `data.undone_by`，不回写原审计。
- `POST /api/drafts/{id}/confirm`：沿用原草稿正式确认和收据；不可绕过预览直接保存批次。
- `DELETE /api/drafts/{id}`：沿用原草稿取消。校历草稿不可通过通用PUT重定向或改写；修改输入后重新预览。

停课示例（日期为原课日期，结束日包含）：

```json
{
  "operation": "apply",
  "rule_kind": "practice_week",
  "title": "经确认的第二周实践安排",
  "reason": "教务处通知第3条，2026-10-10",
  "source_scope": "仅所选理论课，第二周停课，不含实验课",
  "course_ids": ["course-a", "course-b"],
  "action": "cancel",
  "start_date": "2026-10-19",
  "end_date": "2026-10-25",
  "mappings": []
}
```

补课使用同一模型，`action=move`、`start_date=end_date=null`，并填写：

```json
{"mappings": [{"original_date": "2026-10-21", "target_date": "2026-10-24"}]}
```

撤销也先生成原草稿：

```json
{"operation": "undo", "batch_id": "confirmed-batch-id", "reason": "撤销本次学校通知"}
```

## 公共集成接点

`validate_semester_payload(payload)` 返回归一化 JSON；`imports.validate_payload` 对 `semester_calendar` 调用它。`imports.edit_draft` 禁止该类型通用修改。`imports.commit_draft` 对该类型检查 `source_revision`，然后调用 `save_semester(db, owner, draft, payload)`，服务返回 `saved_ids`。父提交事务继续负责设置版本递增、原草稿状态、摘要和receipt。

`preview_semester(db, owner, payload)` 与保存均使用原 `calendar.expand_calendar`、`occupied_course_events` 和 `conflicts.detect_conflicts`，不增加另一套课表或排程器。补课例外的来源标记为：

```json
{"kind":"semester_calendar","preserve_periods":true,"original_date":"2026-10-21","target_date":"2026-10-24"}
```

`date` 仍为原课日期；`starts_at/ends_at` 为目标日期完整本地起止。统一展开器依据该标记平移原分段。保存时附加 `draft_id`、`batch_id`、用户依据和作用范围。补课还由服务端生成 `source.interval_snapshot`（授课/课间/占用及版本）并保存确认时的 `source.timezone`，均绑定完整预览hash，禁止作为请求字段传入。已确认补课在后续节次钟点、课程节次或显示时区变更后仍沿用当时确认的显式分段；撤销恢复原例外，并按当前课程设置展开。避免把后续配置变化误当补课数据损坏而阻断整张课表。

`source.preview` 字段：

| 字段 | 含义 |
| --- | --- |
| `schema_version` / `interval_version` | 校历服务和统一课程分段版本 |
| `timezone` / `operation` / `undo_of` | 本次解释时区、保存或撤销、原批次 |
| `changes[]` | `course_id,date,title,before,after`，before/after是统一展开的具体课程或null |
| `targets[]` / `mutations[]` | 确切原课范围、旧例外快照及替换/恢复动作 |
| `versions` / `preview_hash` | 设置与课程、例外、固定事项、计划、禁排、批次来源版本；完整预览hash |
| `conflict_report` | 原统一冲突模型，仅保留本批实际课程相关重叠/转移/未知信息 |
| `affected_plans` / `plan_conflicts` | 调整前或后受影响的原计划；新课时间重叠的计划，含locked |

`semester_calendar_changed` 规划事件包含 `batch_id,operation,undo_of,before,after,preview`，供原事实变化/重排入口消费；不自动移动任何已保存计划、执行记录、任务或锁定项。

前端挂载：`SemesterCalendar({timezone})` 提供学校规则、课程勾选、日期范围/映射和历史撤销；原 `DraftReview` 对校历草稿显示 `SemesterCalendarReview({draft})`，仍由 `DraftActions` 二次确认。若将其加入统一冲突复核类型，应从新鲜 `preview_semester` 返回同一 `conflict_report`，把 `versions` 绑定到冲突token，避免在另一处重建例外逻辑。

## 保存、撤销与审计

确认前验证owner、草稿状态、payload hash、源设置revision、课程展开版本、所有来源revision和重算预览hash，任一失效返回409/422，批次不部分生效。每个原课保留原canonical exception ID（若有），使重复active例外失效；原例外的完整payload存入不可变 `semester_calendar_batch`。批次和规划事件与所有例外同事务保存。服务使用savepoint；SQLite还显式保证外层BEGIN，避免只读确认开始时RELEASE意外提交，使后续receipt或草稿失败仍能回滚整批。

撤销不会简单把active改为false：它逐项核对原批次保存后所有例外ID、revision、完整payload及同次新记录，任何后续修改或新增重复例外均409，保护之后的用户调整。通过检查后恢复原来的每一份例外payload（含旧版多个active/inactive记录），仅删除本批新建的例外；恢复时revision递增。其他原课、其他批次的例外不变。撤销生成新批次和新规划事件，不修改原批次或原before/after审计。已撤销批次、撤销记录自身不接受再次撤销。

## 验证与验收范围

`backend/tests/test_semester_calendar.py` 使用隔离临时SQLite；覆盖多课多日期实践停课、明确节假日补课映射及冲突、分段保留、无规则拒绝、owner/hash/revision、幂等receipt、写后中断整批回滚、外层确认失败回滚、旧例外精确恢复、后续修改/新duplicate拒绝、跨时区及DST缺失/重复、重启与原draft路由。

`frontend/src/semester-calendar-state.test.ts` 覆盖未知规则/日期不推断、只发送明确范围或映射、重复源日/倒置范围拒绝、丢失响应原样重试及输入变化更换操作。

这些是合成规则的实现验收。真实学校校历、实践通知、节假日补课内容和真实用户完整操作仍需实际资料，不能据此宣称真实学校规则专项已验收。
