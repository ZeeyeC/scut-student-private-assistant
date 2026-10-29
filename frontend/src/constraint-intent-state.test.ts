import {describe,it,expect} from 'vitest';
import {constraintIntentForm,constraintIntentChanges,newConstraintIntentOperation} from './constraint-intent-state';

describe('constraint clarification state',()=>{
  it('keeps clock unknown and overnight explicit',()=>{
    const form=constraintIntentForm();
    expect(form.start_time).toBe('');expect(form.end_time).toBe('');
    const body=constraintIntentChanges({...form,day_expression:'这周三'});
    expect(body.start_time).toBeNull();expect(body.end_time).toBeNull();
    expect(body.end_day_offset).toBe(0);
  });
  it('retains exactly the original payload for a lost response retry',()=>{
    const body={revision:2,changes:{start_time:'14:00'}};
    const op=newConstraintIntentOperation('/constraint-intents/one','PATCH',body);
    body.changes.start_time='17:00';
    expect(op.body.changes.start_time).toBe('14:00');
    expect(op.idempotencyKey).toBeTruthy();expect(op.path).toBe('/constraint-intents/one');
  });
});
