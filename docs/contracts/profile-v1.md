# 用户确认画像契约 profile-v1（B4 / T07 独立交付）

本契约只提供用户明确设置的软偏好、读取与重置。没有执行样本时保持未知；不生成习惯、系统建议或第二套硬约束。本版尚未实现画像对排程结果的影响，不能据此宣称 T07 的“同条件下深度任务优先安排、修改后下一方案生效”验收通过。A 侧 T04/T06 输入与规划器接入、真实对照样本验收仍待完成。

## 接入入口

- 后端：`profile_router(get_db, current_user)`，位于 `backend/app/profile_routes.py`。调用 `app.include_router(profile_router(get_db, current_user))`。
- `get_db` 必须沿用现有 `BEGIN IMMEDIATE` / commit / rollback 的完整请求事务。领域函数不自行提交事务；画像、全局来源版本、变更事件和幂等回执共同提交或回滚。
- 前端：`PersonalProfile` 命名与默认导出，位于 `frontend/src/PersonalProfile.tsx`。在现有 `QueryClientProvider` 下直接挂载；使用现有 `api` 的身份验证和 CSRF，查询键为 `['personal-profile']`。
- 不更改模型工具白名单，不让模型直接写正式画像，不创建新数据库、表或 Key。

## HTTP 接口

### GET `/api/profile`

身份验证后只读当前用户画像，无请求体。读取不存在的画像不会写入任何 Resource、settings 或回执。

```json
{
  "id": null,
  "kind": "user_profile",
  "revision": 0,
  "source_revision": 0,
  "contract_version": "profile-v1",
  "data": {
    "schema_version": 1,
    "timezone": null,
    "effective_from": null,
    "effective_until": null,
    "preferences": {
      "preferred_study_windows": null,
      "energy_windows": null,
      "focus_minutes": null,
      "break_minutes": null,
      "review_interval_days": null,
      "daily_load_minutes": null,
      "leisure_protection": null
    },
    "source": "unknown",
    "confirmed": false,
    "sample_count": 0,
    "updated_at": null
  },
  "suggestions": []
}
```

已有画像返回稳定的用户范围 `id` 和递增 `revision`。`source_revision` 是现有 settings Resource 的当前全局版本；不存在 settings 时返回 0，不创建默认设置。画像更新触发现有 `store.bump`，首次写入时若 settings 尚不存在，现有 store 会创建 revision 1 再递增到 2。

`schema_version: 1` 描述存储数据；`contract_version: profile-v1` 描述 API。`source`、`confirmed`、`sample_count`、`updated_at` 都由服务端写入，不能由客户端冒充。

### PUT `/api/profile`

必须提供 `Idempotency-Key` 请求头。请求完整替换当前软偏好：未提供的偏好变为 `null`，不会继承或推断习惯。

```json
{
  "revision": 0,
  "data": {
    "timezone": "Asia/Shanghai",
    "effective_from": "2026-10-01",
    "effective_until": "2026-12-31",
    "preferences": {
      "preferred_study_windows": [
        {"weekdays": [1, 2, 3, 4, 5], "start": "19:00", "end": "21:00", "task_type": "deep"}
      ],
      "energy_windows": [
        {"weekdays": [1, 2, 3, 4, 5], "start": "19:00", "end": "21:00", "level": "high"}
      ],
      "focus_minutes": 45,
      "break_minutes": 10,
      "review_interval_days": 3,
      "daily_load_minutes": 120,
      "leisure_protection": "prefer_protect"
    }
  }
}
```

返回同 GET 形状。每次成功的非重放写入令画像 revision 加 1，服务端记 `source: user`、`confirmed: true`、`sample_count: 0` 和 UTC `updated_at`。样本量 0 指未使用任何执行样本推断；用户选择不是执行样本。

### POST `/api/profile/reset`

必须提供 `Idempotency-Key` 请求头。请求体只有 `{"revision": 1}`，返回同 GET 形状。清空时区、有效范围及全部软偏好为 `null`，保留画像身份并递增版本；`source: user`、`confirmed: true` 表示用户明确清空，绝不表示已确认某种习惯。课程、任务、现有硬约束和执行事实不被删除。

## 校验与未知语义

| 字段 | 范围 / 含义 |
| --- | --- |
| `revision` | 严格整数，≥0；0 仅适用于尚无画像。 |
| `timezone` | PUT 必填有效 IANA 时区；未设置/重置后的 GET 可以为 null。 |
| `effective_from`, `effective_until` | ISO 日期或 null；起止日期均包含在有效范围；null 表示该方向不限定，截止不得早于起始。以后消费画像时按其时区判断当地日期。 |
| `preferred_study_windows` | null 未知；[] 明确不指定时段；最多 28 项。 |
| `energy_windows` | null 未知；[] 明确不指定精力时段；最多 28 项。 |
| `weekdays` | 1=周一，7=周日；1–7 个不重复严格整数。 |
| `start`, `end` | 不带时区的当地整分钟时间，结束必须晚于开始；同类时段同一天不能重叠。跨午夜需拆分；返回时间标准化为 `HH:mm:ss`。 |
| 学习 `task_type` | `any`、`deep`、`review`；API 省略时为 any，不推断具体学习类型。界面要求主动选择。 |
| 精力 `level` | `low`、`medium`、`high`，必填；粗粒度自述，不是模型测量。 |
| `focus_minutes` | null 或 5–240 严格整数。 |
| `break_minutes` | null 或 0–120 严格整数。0 与未知不同。 |
| `review_interval_days` | null 或 1–365 严格整数。 |
| `daily_load_minutes` | null 或 0–720 严格整数，表达偏好负荷，不覆盖现有硬上限。 |
| `leisure_protection` | null 未知；`prefer_protect` 优先保护休闲；`flexible` 允许灵活取舍；都不是硬约束。 |

写入对象及嵌套对象均禁止额外字段。数字字符串、布尔值和小数不被接受为整数偏好。时段与精力值都不能用历史计划时长或模型猜测自动填充。

## 幂等、隔离与原子性

- 现有 `Resource(kind='user_profile')` 存储每用户唯一画像，ID 由用户身份派生。客户端不能指定 owner 或画像 ID，查询和修改仅使用已验证的 `current_user.id`；领域读取还检查 Resource 的 owner 和 kind。
- `Receipt` 分别使用 `profile-replace`、`profile-reset` 作用域；Key 不能为空且不得超过 160 字符。同一用户、作用域、Key 和相同请求体返回原响应，即使其旧 revision 已失效；Key 换内容返回 409。重放不重复 bump 或生成事件。回执中的 `source_revision` 是原响应的快照；重新 GET 可读取当前全局版本。
- 非重放的旧 revision 返回 409；未验证身份返回 401；缺少 Key、格式不合法或越界字段返回 422。
- 每次成功写入通过现有 `record_change` 记录 `profile_changed`，`source_id` 为画像 ID，`source_revision` 为画像 revision。事件 `details` 包含 `action: replace|reset`、`profile_revision`、全局 `source_revision` 和 `contract_version`，不复制个人偏好到事件。
- 已有规划草稿可通过既有全局来源版本机制识别输入变更；这不等于规划器已使用画像评分或完成 T07 对照验收。

## 系统建议与后续消费边界

`suggestions` 本版固定为空，不提供生成、直接写入或采纳接口。后续系统建议必须另外表达来源、样本量、依据和有效范围，并保持 `confirmed: false`；只有用户明确采纳才能转为正式用户偏好。不得直接改本契约的 `source: user` 来伪造确认。

A 侧消费时应先确认 `data.confirmed`、字段非 null、有效日期范围及版本，然后把字段作为软偏好输入；空数组和显式 0 要保持原义。未知字段继续使用明确命名的现有默认规则，不能称为“已了解用户习惯”。A 侧需另补同条件对照和下一方案生效测试。

## 验证范围

新增后端隔离 FastAPI/SQLite 测试覆盖纯读取、显式确认、幂等、陈旧版本、用户隔离、重置保留任务课程、格式范围和事务回滚。前端测试覆盖未知/0/空数组、编辑隔离、必选项、重试请求快照及真实组件服务端渲染的来源标签；生产页面挂载及浏览器点击验收由集成方补充。未进行付费模型测试，也未把排程联动标为成功。
