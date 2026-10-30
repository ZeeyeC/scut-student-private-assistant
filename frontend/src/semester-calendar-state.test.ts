import {describe,it,expect} from 'vitest';
import {newSemesterForm,semesterPayload,semesterOperation,updateSemesterForm} from './semester-calendar-state';

describe('explicit semester rules',()=>{
  it('requires school rule and selected courses and does not guess holiday makeup dates',()=>{
    expect(()=>semesterPayload(newSemesterForm())).toThrow();
    const form={...newSemesterForm(),rule_kind:'holiday' as const,title:'学校通知',reason:'教务处第3条',source_scope:'选中课程，仅10月14日',course_ids:['math'],action:'move' as const};
    expect(()=>semesterPayload(form)).toThrow(/映射/);
    expect(()=>semesterPayload({...form,mappings:[{original_date:'2026-10-14',target_date:''}]})).toThrow();
  });
  it('sends only the explicitly selected date range or mappings',()=>{
    const base={...newSemesterForm(),rule_kind:'practice_week' as const,title:' 实践周 ',reason:' 教务通知 ',source_scope:' 本学期1至2周 ',course_ids:['math','physics'],start_date:'2026-10-12',end_date:'2026-10-25'};
    expect(semesterPayload(base)).toEqual({operation:'apply',rule_kind:'practice_week',title:'实践周',reason:'教务通知',source_scope:'本学期1至2周',course_ids:['math','physics'],action:'cancel',start_date:'2026-10-12',end_date:'2026-10-25',mappings:[]});
    expect(semesterPayload({...base,action:'move',mappings:[{original_date:'2026-10-14',target_date:'2026-10-18'}]})).toMatchObject({action:'move',start_date:null,end_date:null,mappings:[{original_date:'2026-10-14',target_date:'2026-10-18'}]});
  });
  it('retries the exact lost-response request and discards a retry when input changes',()=>{
    const body={operation:'undo',batch_id:'one',reason:'恢复原通知'};
    const op=semesterOperation(body);body.reason='变更';
    expect(op.body.reason).toBe('恢复原通知');expect(op.key).toBeTruthy();
    const state=updateSemesterForm({form:newSemesterForm(),operation:op},{title:'新通知'});
    expect(state.operation).toBeNull();expect(state.form.title).toBe('新通知');
  });
  it('rejects reversed range and duplicate source mappings',()=>{
    const base={...newSemesterForm(),rule_kind:'custom' as const,title:'通知',reason:'明确来源',source_scope:'明确范围',course_ids:['math'],start_date:'2026-10-20',end_date:'2026-10-12'};
    expect(()=>semesterPayload(base)).toThrow(/日期/);
    expect(()=>semesterPayload({...base,action:'move',mappings:[{original_date:'2026-10-14',target_date:'2026-10-18'},{original_date:'2026-10-14',target_date:'2026-10-19'}]})).toThrow(/原课日期/);
  });
});
