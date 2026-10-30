export type SemesterForm={rule_kind:''|'practice_week'|'holiday'|'makeup'|'custom';title:string;reason:string;source_scope:string;course_ids:string[];action:'cancel'|'move';start_date:string;end_date:string;mappings:{original_date:string;target_date:string}[]};
export type SemesterOperation={body:any;key:string};
export function newSemesterForm():SemesterForm{return {rule_kind:'',title:'',reason:'',source_scope:'',course_ids:[],action:'cancel',start_date:'',end_date:'',mappings:[]};}
export function semesterPayload(form:SemesterForm){
  if(!form.rule_kind||!form.title.trim()||!form.reason.trim()||!form.source_scope.trim()||!form.course_ids.length)throw new Error('请明确学校规则、依据、作用范围并选择课程');
  if(form.action==='cancel'&&(!form.start_date||!form.end_date||form.end_date<form.start_date))throw new Error('请填写有效原课日期范围');
  if(form.action==='move'&&(!form.mappings.length||form.mappings.some(m=>!m.original_date||!m.target_date)))throw new Error('补课必须逐项填写原课日期与目标日期映射');
  if(form.action==='move'&&new Set(form.mappings.map(m=>m.original_date)).size!==form.mappings.length)throw new Error('一个原课日期只能填写一次映射');
  return {operation:'apply' as const,rule_kind:form.rule_kind,title:form.title.trim(),reason:form.reason.trim(),source_scope:form.source_scope.trim(),course_ids:[...form.course_ids],action:form.action,start_date:form.action==='cancel'?form.start_date:null,end_date:form.action==='cancel'?form.end_date:null,mappings:form.action==='move'?form.mappings.map(m=>({...m})):[]};
}
export function semesterOperation<T>(body:T){return {body:JSON.parse(JSON.stringify(body)) as T,key:crypto.randomUUID()};}
export function updateSemesterForm(state:{form:SemesterForm;operation:SemesterOperation|null},patch:Partial<SemesterForm>){return {form:{...state.form,...patch},operation:null};}
