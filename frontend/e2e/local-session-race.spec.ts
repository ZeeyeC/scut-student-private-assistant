import {test,expect} from '@playwright/test';
test('successful local session wins over a stale profile-selection snapshot during first startup',async({page})=>{
  await page.route('**/api/local/session',async route=>{
    const response=await route.fetch();expect(response.ok()).toBe(true);
    await page.evaluate(async()=>{
      const {queryClient}=await import(/* @vite-ignore */ '/src/main.tsx');
      queryClient.setQueryData(['local-profile'],{selected:false,needs_selection:true,profiles:[{id:'synthetic-stale-snapshot',email:'fixture@example.invalid',resource_count:0}]});
    });
    await route.fulfill({response});
  });
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'今日',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'检测到已有资料',exact:true})).toHaveCount(0);
  const me=await(await page.request.get('/api/me')).json();expect(me.id).toBeTruthy();
  await page.unroute('**/api/local/session');await page.reload();
  await expect(page.getByRole('heading',{name:'今日',exact:true})).toBeVisible();
  expect((await(await page.request.get('/api/me')).json()).id).toBe(me.id);
});
