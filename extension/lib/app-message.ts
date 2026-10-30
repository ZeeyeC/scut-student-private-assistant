export function importPageAllows(path:string,action:unknown,payload:unknown):boolean {
  if(!path.startsWith('/school-import/'))return true;
  const id=/^\/school-import\/([a-f0-9-]{36})$/.exec(path)?.[1];
  if(!id)return false;
  if(action==='detect')return true;
  return typeof action==='string'&&['start','restore','stop'].includes(action)&&!!payload&&typeof payload==='object'&&(payload as {sessionId?:unknown}).sessionId===id&&typeof (payload as {bindingGeneration?:unknown}).bindingGeneration==='string'&&/^[a-f0-9-]{36}$/.test((payload as {bindingGeneration:string}).bindingGeneration);
}
