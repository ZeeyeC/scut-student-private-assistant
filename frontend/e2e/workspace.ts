import {expect,type Page} from '@playwright/test';

type Destination='courses'|'calendar'|'planning'|'rules'|'preferences'|'semester'|'reminders'|'models'|'data'|'goals'|'review'|'tasks'|'import'|'records'|'fixed';
// Exercise the same visible controls used in the App, including closing drawers.
export async function workspace(page:Page,destination:Destination){
  for(let i=0;i<6;i++){
    if(!await page.getByRole('dialog').count())break;
    await page.keyboard.press('Escape');
  }
  const settings=['preferences','semester','reminders','models','data'].includes(destination);
  if(destination==='records'){await page.getByRole('button',{name:'今日',exact:true}).click();await page.getByRole('button',{name:'执行与记录',exact:true}).click();return;}
  const task=['tasks','goals','review'].includes(destination);
  await page.getByRole('button',{name:settings?'设置':task?'任务':'日程',exact:true}).click();
  const control:Partial<Record<Destination,string>>={courses:'课程',import:'导入课表',fixed:'固定事项',planning:'安排学习',rules:'课程规则',preferences:'学习偏好',semester:'课程与学期',reminders:'提醒与桌宠',models:'模型连接',data:'资料与备份',goals:'目标',review:'复盘'};
  if(!settings&&!task)await page.getByRole('button',{name:'全部',exact:true}).click();
  if(control[destination])await page.getByRole('button',{name:control[destination],exact:true}).click();
  if(destination==='review')await expect(page.getByRole('region',{name:'每周复盘',exact:true})).toBeVisible();
}
export async function inbox(page:Page,tab:'草稿'|'建议'|'时长'='草稿'){
  for(let i=0;i<6&&await page.getByRole('dialog').count();i++)await page.keyboard.press('Escape');
  await page.getByRole('button',{name:/^待确认(?: · \d+)?$/}).click();
  await page.getByRole('dialog',{name:'待确认',exact:true}).getByRole('button',{name:tab,exact:true}).click();
}

export async function negotiation(page:Page){await workspace(page,'review');await page.getByText('调整下一周安排',{exact:true}).click();}
