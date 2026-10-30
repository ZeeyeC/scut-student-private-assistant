export type BrowserSettings={browser:'chrome'|'edge';installed:boolean};
declare global { interface Window { __campusNative?:{request:<T=unknown>(command:string,payload?:Record<string,unknown>)=>Promise<T>}; } }
export function nativeImport<T>(command:string,payload:Record<string,unknown>={}):Promise<T>{
  if(!window.__campusNative)return Promise.reject(new Error('请在独立App中使用学校导入。'));
  return window.__campusNative.request<T>(command,payload);
}
