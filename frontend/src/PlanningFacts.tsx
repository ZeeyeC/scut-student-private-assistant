type Facts={execution?:Record<string,any>;profile?:Record<string,any>;goals?:Record<string,any>};

export function PlanningFacts({execution,profile,goals}:Facts) {
  const steps=Object.entries(execution?.steps??{}) as [string,any][];
  return <details aria-label="规划事实依据"><summary>查看执行、档案和目标依据</summary>
    {execution?.integration&&<>
      <p>已知实际投入小计 {execution.known_actual_minutes} 分钟 · 完整实际总量 {execution.actual_minutes===null?'未知':`${execution.actual_minutes} 分钟`}。任务完成状态与计时、投入分别记录。</p>
      {steps.map(([id,s])=><p key={id}>步骤 {id}：实际 {s.actual_minutes===null?'未知':`${s.actual_minutes} 分钟`} · 旧估算 {s.legacy_estimated_minutes} 分钟 · 用于规划的已投入 {s.planning_spent_minutes} 分钟 · 有效记录 {s.effective_record_ids.length} 条 · 未确认区间 {s.unconfirmed_execution_ids.length} 条</p>)}
    </>}
    {profile?.application&&<>
      <p>个人档案版本 {profile.revision} · {profile.application.active_at_planning_time?'当前已确认且有效':'当前未确认或不在有效期内，不套用隐含习惯'} · 来源 {profile.data.source} · 时区 {profile.data.timezone??'未知'}</p>
      <p>已配置字段：{profile.application.configured_fields.join('、')||'无'}。专注、休息和负荷参与分块；学习时段、精力和休闲偏好用于偏好方案；复习间隔用于明确的复习候选。</p>
      {Object.entries(profile.application.deferred_fields).map(([key,value])=><p key={key}>待补资料：{key} · {String(value)}</p>)}
    </>}
    {goals?.integration&&<>
      <p>{goals.dedupe_rule}</p>
      {goals.weeks.map((g:any)=><p key={`${g.goal_id}:${g.week_start}`}>目标 {g.goal_id} · {g.week_start} 当周：预算 {g.weekly_budget_minutes} 分钟 · 已知实际小计 {g.known_actual_minutes} 分钟 · 已排 {g.planned_minutes} 分钟 · 尚缺 {g.unmet_budget_minutes} 分钟 · {({reduce:'允许减负',delay:'仅在期限内延后',ask:'不足时询问，不自动部分分配'})[g.allowed_adjustment as string]}。{g.reason}</p>)}
    </>}
  </details>;
}
