import {ChevronRight} from 'lucide-react';
import {formatBytes,uploadedDate,type LibraryItem} from './knowledge-library';
export function LibraryFileList({items,onOpen}:{items:LibraryItem[];onOpen:(id:string)=>void}){
 return <><div className="kb-tablehead" aria-hidden="true"><span>文件名称</span><span className="kb-coursecell">所属课程</span><span className="kb-date">上传时间</span><span/></div>
 <div className="kb-file-list" role="list" aria-label="已上传资料">{!items.length?<p className="kb-empty">暂无匹配资料</p>:items.map(f=><div className="kb-file" role="listitem" key={f.id}>
 <button type="button" className="kb-filename" onClick={()=>onOpen(f.id)} aria-label={`查看 ${f.data.filename}`}><span className="kb-filetype">{f.data.format==='web'?'网页':f.data.format.toUpperCase().slice(0,3)}</span><span><span className="kb-name">{f.data.filename}</span><span className="kb-filemeta">{f.data.format==='web'?'网页资料':formatBytes(f.data.size_bytes)}</span></span></button>
 <span className="kb-cell kb-coursecell">{f.data.course_missing?'原课程已移除':f.data.course_name||'未分类'}</span><span className="kb-cell kb-date">{uploadedDate(f.data.created_at)}</span><button type="button" className="kb-icon" onClick={()=>onOpen(f.id)} aria-label={`${f.data.filename}的详情`}><ChevronRight size={18}/></button>
 </div>)}</div></>;
}
