import {createContext} from 'react';
export const ReviewContext=createContext<{count:number;open:()=>void}|null>(null);
