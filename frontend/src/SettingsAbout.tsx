import {useEffect,useState} from 'react';
import {nativeImport} from './native-import';
import {Button} from './components/ui/button';
type Attribution={status:string;repository?:string;upstream_ref?:string;message?:string;declarations:{name:string;text:string}[]};
export function SettingsAbout(){
  const [value,setValue]=useState<Attribution>(),[error,setError]=useState(''),[copied,setCopied]=useState(false);
  useEffect(()=>{let mounted=true;nativeImport<Attribution>('get-pet-attribution').then(data=>{if(mounted)setValue(data);}).catch(()=>{if(mounted)setError('请在独立App中查看本机素材声明。');});return()=>{mounted=false;};},[]);
  return <section className="card" aria-label="关于课间"><h2>关于课间</h2><p>本机学生助手</p>
    {error&&<p>{error}</p>}{value?.message&&<p>{value.message}</p>}
    {value?.status==='installed'&&<><p>角色来源：NaiWaChatPet</p><p className="about-source">{value.repository}<br/>{value.upstream_ref}</p><Button variant="outline" onClick={async()=>{try{await navigator.clipboard.writeText(value.repository+'\n'+value.upstream_ref);setCopied(true);}catch{setError('复制失败，可选中上方来源文字复制。');}}}>{copied?'已复制来源':'复制来源'}</Button>
      {value.declarations.map(item=><details key={item.name}><summary>{item.name}</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',fontSize:12}}>{item.text}</pre></details>)}</>}
  </section>;
}
