# 周复盘 v1：统计事实与改进意向

本契约属于 B5/T12 的独立部分。读取既有计划快照、当前安排、执行更正链及历史估算；保存用户原因和下周调整意向。不会调用模型、生成排程或修改正式安排。下一周优化需要甲方排程服务，仍待联调及真实样本验收。

## 接入

后端：`from app.review_routes import review_router`，`app.include_router(review_router(get_db, current_user))`。`get_db` 应沿用已序列化、可原子提交/回滚的事务依赖。

前端：`import { WeeklyReview } from './WeeklyReview'`，在现有 React Query provider 下挂载 `<WeeklyReview />`，无 props。组件读取现有 `/api/settings`，用保存时区确定初始周；允许选择周内日期（归一到周一）和明确指定报告时区。来源 ID 放在展开详情中。

## GET `/api/weekly-review?week_start=2026-10-26&timezone=Asia%2FShanghai`

`week_start` 必须是当地周一。`timezone` 可省略，使用保存的设置时区；无设置使用产品默认 `Asia/Shanghai`，读取不创建设置。区间为当地周一零点至下周一零点，左闭右开；先构造当地午夜，再转 UTC，支持跨年及夏令时。无登录返回 401，非周一、无效日期、无效 IANA 时区返回 422。

返回 `contract_version: weekly-review-v1`，`week_start/week_end/timezone/starts_at/ends_at/source_revision`，以及以下对象：

| 字段 | 内容和边界 |
| --- | --- |
| `plans.original` | 逐日选择覆盖当日的最早批准快照，按安排 ID 去重、按日裁切。不是把快照整体累加。只有完整覆盖七天且都在周开始前有依据，才能称完整原始周基线。 |
| `plans.adjusted` | 逐日选择覆盖当日的最近批准快照，同样去重及裁切。不同日可引用不同快照。 |
| `plans.current` | 当前 `plan_block` 在本周区间的实际计划长度。空安排为已知 0；这是当前安排视图，不冒充历史基线。 |
| 每个计划视图 | `status: complete/partial/missing`；`minutes` 仅完整时有值；`known_minutes` 为已知部分，缺基线不得用 0 冒充原始计划；另含 `covered_dates/snapshot_ids/blocks/gaps`。每块有 `plan_block_id/task_id/title/seconds/snapshot_ids`。 |
| `execution.actual_seconds/actual_minutes` | 有有效记录且没有缺失安排、日期归属歧义、待确认离线区间时才返回已记录实际合计。否则为 `null`。明确反馈未开始且实际 0 仍是 0。分钟在秒数汇总后转换。 |
| `execution.observed_seconds` | 可以可靠归入本周的已记录投入小计。无任何可靠时长则 `null`，有可靠的显式 0 则 0；有其他缺口时仍可展示此小计。不能把它当完整总量。 |
| `execution.effective_record_ids` | 更正链的当前尾记录；被替代记录不参与求和。 |
| `execution.records` | 当前有效记录，保留执行/任务/步骤/安排/计时引用、原始 `performed_on/timezone/source`、本周归属的 `observed_seconds/actual_seconds`、`feedback/unfinished_reason/reason_prompt/supersedes_id`、`allocation_status` 与 `completion_allocation_status`。 |
| `execution.missing_plan_block_ids` | 原始、调整后、当前视图中出现而没有本周可归属执行覆盖的安排；历史估算不能填补为实际。 |
| `execution.ambiguous_record_ids` | 无法可靠归周的记录，不进入已记录投入小计。 |
| `execution.unconfirmed_execution_ids` | 有未确认的离线区间，保留已观测秒数但实际总量未知。 |
| `execution.completed_task_ids` | 有可靠本周日期依据且显式 `task_status=completed` 的去重任务。`feedback=completed` 只是本次执行完成，不自动代表整项任务完成。 |
| `execution.completed_feedback_record_ids` | 本周完成的执行反馈，单独提供。 |
| `execution.ambiguous_completion_record_ids` | 有完成事实但跨周计时不能确定完成日期的记录，不在两周重复计任务完成。 |
| `execution.undated_completed_task_ids` | 当前状态已完成但无带日期完成执行事实的任务；仅说明日期缺口，不能算成本周完成数。 |
| `estimates.allocated_minutes/allocations` | 可归本周且未被有效执行覆盖替代的历史估算，始终单列。 |
| `estimates.unallocated` | 未知归属周的旧估算，包括跨周安排的聚合估算；`week_attribution=unknown`，不加入本周估算合计。 |
| `gaps` | 基线不足、迟录基线、时区不一致、快照或时间无效、执行缺失、跨周归属歧义、离线间隔、未确定完成日期等事实缺口。 |
| `review` | 本周、本报告时区的用户复盘 Resource；无记录时 `id=null/revision=0/status=awaiting_choice/history=[]`。 |
| `next_week_optimization` | 固定 `pending_integration`，不声称下周优化已经应用。 |

### 快照与归周的保守规则

- 日快照可贡献已知部分，不能被当成整周原始计划。快照时区与报告时区不一致时，保留 `snapshot_timezone_mismatch`，不猜测其本地日期覆盖范围。
- `plan_snapshot`、其 `previous_blocks` 和 `inputs` 不改写；不把 `previous_blocks` 伪装成经过确认的整周原始基线。来源快照 ID 可追溯完整批准依据。
- 手工记录的 `performed_on/timezone` 是事实。报告时区变化后，将该事实表示为原时区的整日区间：整日落在本周才计入，整日在外才排除；仅部分重叠时标为歧义。不会猜一个执行时刻。
- 计时记录只用其 `execution_timer.segments` 中可靠的带偏移时间戳拆周。跨边界时，墙钟跨度与单调计时秒数明显不符、重叠/无序片段、缺片段或片段不能解释保存的秒数，都标为未知，不按计划长度补齐。完全位于一周的片段保留其单调观测秒数。
- 计时保存秒数为片段累计的整数部分；跨周用累计位置取整数，确保相邻周之和等于保存的执行秒数，不因亚秒片段重复进位。零秒计时反馈仍是明确事实。
- 更正后来源为 `manual`，按更正后的手工事实归周，不重复计入旧计时片段。
- 不会从缺记录、计划差额或原因空缺推断“缺乏自律”。已有用户原因原样保留代码和中文标签，未记录原因时给出中性追问。

## POST `/api/weekly-review/actions`

请求头 `Idempotency-Key` 必填。示例：

```json
{
  "week_start": "2026-10-26",
  "timezone": "Asia/Shanghai",
  "revision": 0,
  "source_revision": 7,
  "action": "accept",
  "reason": "下周想把晚间学习前移"
}
```

- `action`: `reason` 保存用户原因；`accept` 保存用户描述的调整意向；`reject` 暂不采纳；`restore` 恢复待选择。`accept/reason` 需要非空原因或意向，最多 2000 字。
- `revision` 为对应 `review.revision`；`source_revision` 为报告读取时的全局资料版本。任一过期返回 409，前端刷新后重新核对。
- 返回 `kind=weekly_review` Resource，`data.status` 为 `awaiting_choice/accepted_pending_integration/rejected`，包含 `reason/history/source_revision/week_start/timezone`。
- 用户独立拥有每周/时区 Resource；所有动作追加历史，同时递增 Resource 版本与全局资料版本、产生 `weekly_review_changed` 事件；`Resource + Receipt + event + global revision` 在同一事务，失败整体回滚。
- 相同幂等键和相同内容重放原回执，相同键不同内容返回 409；重启后仍可读回历史。
- 接受只代表确认用户自己的改进意向，状态明确待接入；**不创建或修改正式计划、不改执行事实、不调用甲方未交付接口**。后续排程必须走正式计划草稿确认。

## 验证与未验收

独立测试：`backend/.venv/bin/python -m pytest backend/tests/test_weekly_review.py -q`。17 项使用临时 SQLite 和真实 FastAPI 路由，覆盖 60 分钟计划 / 25 分钟实际 / 更正 20、未知和 0、历史估算、重复快照、每日部分基线、跨周跨年及夏令时、时区变化、可靠/不可靠计时片段、亚秒守恒、完成事实、版本/幂等/归属/回滚/重启。前端 `weekly-review-state.test.ts` 与 `WeeklyReview.test.tsx` 5 项覆盖本地周、未知/0/秒数展示、意向版本及来源展示；类型检查通过。

尚未验收：父任务统一挂载后的真实浏览器流程、全项目回归、真实用户执行样本与下周排程效果、甲方 T04/T06/T11 联调。静态组件渲染和固定样本测试不等于这些场景通过。
