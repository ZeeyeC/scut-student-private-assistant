import type {Resource} from './types';

export type ConstraintIntentForm={day_expression:string;start_time:string;end_time:string;end_day_offset:number;recurrence:'once'|'weekly';weekdays:number[];valid_until:string;strength:'hard'|'soft';timezone:string};
export function constraintIntentForm(row?:Resource):ConstraintIntentForm{
  const p=row?.data.fields??{};
  return {day_expression:p.day_expression??'',start_time:p.start_time??'',end_time:p.end_time??'',end_day_offset:p.end_day_offset??0,recurrence:p.recurrence??'once',weekdays:p.weekdays??[],valid_until:p.valid_until??'',strength:p.strength??'hard',timezone:p.timezone??''};
}
export function constraintIntentChanges(form:ConstraintIntentForm){
  return {...form,day_expression:form.day_expression.trim()||null,start_time:form.start_time||null,end_time:form.end_time||null,timezone:form.timezone.trim()||null,valid_until:form.recurrence==='weekly'?(form.valid_until||null):null,weekdays:form.recurrence==='weekly'?form.weekdays:[]};
}
export function newConstraintIntentOperation<T>(path:string,method:string,body:T){
  return {path,method,body:JSON.parse(JSON.stringify(body)) as T,idempotencyKey:crypto.randomUUID()};
}
