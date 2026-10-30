import {useContext,type ReactNode} from 'react';
import {Inbox} from 'lucide-react';
import {ReviewContext} from './review-context';

export function PageHeader({title,meta,children}:{title:string;meta?:ReactNode;children?:ReactNode}){
  const review=useContext(ReviewContext);
  return <header className="page-head"><div className="workspace-page-title"><h1>{title}</h1>{meta&&<small>{meta}</small>}</div><div className="workspace-page-actions">
    {review&&<button className="review-inbox-button" type="button" aria-label={`待确认${review.count?` · ${review.count}`:''}`} onClick={review.open}><Inbox size={16}/><span>待确认</span>{review.count>0&&<span>{review.count}</span>}</button>}{children}
  </div></header>;
}
