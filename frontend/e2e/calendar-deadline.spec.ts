import {test, expect} from '@playwright/test';

test.use({timezoneId:'Asia/Shanghai'});
test('month/day before fills the existing review field; user can save without a date picker', async({page})=>{
  await page.setViewportSize({width:390,height:950});
  await page.goto('/');
  await page.getByRole('button',{name:'助手',exact:true}).click();
  const csrf=(await (await page.request.get('/api/csrf')).json()).csrf_token;
  const year = new Intl.DateTimeFormat('en',{timeZone:'Asia/Shanghai',year:'numeric'}).format(new Date());
  const response=await page.request.post('/api/drafts/assignment',{
    data:{items:[{title:'月日边界验收',due_text:'11月1日之前',due_at:null,uncertain_fields:['due_at']}]},
    headers:{Origin:'http://127.0.0.1:5173','X-CSRF-Token':csrf,'Idempotency-Key':'calendar-boundary'}
  });
  expect(response.ok()).toBe(true);
  await page.reload();
  await page.getByRole('button',{name:'助手',exact:true}).click();
  const review=page.locator('.assignment-review');
  await expect(review.getByLabel('确认后的截止时间')).toHaveValue(`${year}-11-01T00:00`);
  await expect(review.getByText(/已自动填写/)).toBeVisible();
  await expect(review.getByText(/按消息日期/)).toBeVisible();
  await expect(review.getByText(/待确认：截止日期与时间/)).toHaveCount(0);
  expect(await (await page.request.get('/api/tasks')).json()).toHaveLength(0);
  await review.screenshot({path:'/private/tmp/campus-calendar-boundary-review.png'});
  await review.getByRole('button',{name:'校对完成，准备保存'}).click();
  await review.getByRole('button',{name:'确认保存',exact:true}).click();
  await expect(review).toHaveCount(0);
  const tasks = await (await page.request.get('/api/tasks')).json();
  expect(tasks).toHaveLength(1);
  expect(tasks[0].data.due_at).toBe(`${year}-11-01T00:00:00+08:00`);
  await page.reload();
  await page.getByRole('button',{name:'待办 / 作业',exact:true}).click();
  await expect(page.getByRole('heading',{name:'月日边界验收',exact:true})).toHaveCount(1);
});
