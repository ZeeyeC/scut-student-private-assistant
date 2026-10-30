import {expect,it} from 'vitest';
import {importPageAllows} from '../lib/app-message';
const id='7d6ace42-e846-4eba-a704-4fa16c40d076';
it('binds bridge page messages to the import named in its path',()=>{
  expect(importPageAllows('/school-import/'+id,'start',{sessionId:id,bindingGeneration:id})).toBe(true);
  expect(importPageAllows('/school-import/'+id,'start',{sessionId:id})).toBe(false);
  expect(importPageAllows('/school-import/'+id,'restore',{sessionId:'other-import'})).toBe(false);
  expect(importPageAllows('/school-import/'+id,'stop',null)).toBe(false);
});
it('allows detection before binding but rejects malformed bridge paths and unknown commands',()=>{
  expect(importPageAllows('/school-import/'+id,'detect',{})).toBe(true);
  expect(importPageAllows('/school-import/not-an-id','detect',{})).toBe(false);
  expect(importPageAllows('/school-import/'+id,'arbitrary-command',{})).toBe(false);
});
