import {describe,it,expect} from 'vitest';
import {validateDocFiles,isDocFile} from './chat-documents';
import {applyMessage} from './chat-messages';
describe('document attachments',()=>{
 it('accepts supported documents without trusting image MIME',()=>{
  expect(validateDocFiles([new File(['notes'],'notes.md',{type:'text/markdown'})])).toHaveLength(1);
  expect(isDocFile(new File(['x'],'report.pdf',{type:'image/png'}))).toBe(false);
  expect(()=>validateDocFiles([new File(['x'],'run.exe')])).toThrow('仅支持');
 });
 it('caps total documents and per-file bytes',()=>{
  expect(()=>validateDocFiles([new File(['x'],'notes.md')],5)).toThrow('最多');
  const file=new File(['x'],'notes.md');Object.defineProperty(file,'size',{value:21*1024*1024});
  expect(()=>validateDocFiles([file])).toThrow('20 MiB');
 });
 it('preserves selected sources across streaming events',()=>{
  const initial=applyMessage([],{type:'message',run_id:'r',seq:1,payload:{role:'user',message_id:'m',content:'read',source_ids:['s']}});
  const replay=applyMessage(initial,{type:'message',run_id:'r',seq:2,payload:{role:'user',message_id:'m',content:'read'}});
  expect(replay[0].source_ids).toEqual(['s']);
 });
});
