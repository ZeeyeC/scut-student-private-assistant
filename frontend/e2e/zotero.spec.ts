import {test,expect} from '@playwright/test';
test('literature connector defaults off, saves a private token without echo and tests only on click',async({page})=>{
 let config={enabled:false,mode:'local',endpoint:'',connected:null,available:true,tools:[],revision:0,token_configured:false};let tests=0;const secret='synthetic-ui-private-token';
 await page.route('**/api/zotero/status',route=>route.fulfill({json:config}));
 await page.route('**/api/zotero/settings',async route=>{const body=route.request().postDataJSON();expect(body.revision).toBe(config.revision);expect(body.token).toBe(secret);config={...config,enabled:body.enabled,mode:body.mode,endpoint:body.endpoint,token_configured:true,revision:1};await route.fulfill({json:config});});
 await page.route('**/api/zotero/test',async route=>{tests++;if(tests===1)await route.fulfill({json:{connected:true,tools:['zotero_search_items'],read_only:true}});else await route.fulfill({status:422,json:{detail:'连接失败'}})});
 await page.goto('/');await page.getByRole('button',{name:'创建账号',exact:true}).click();await page.getByLabel('邮箱').fill(`zotero-${crypto.randomUUID()}@example.com`);await page.getByLabel('密码').fill('Student!Password2026');await page.getByRole('button',{name:'注册并登录'}).click();
 await page.getByRole('button',{name:'设置',exact:true}).click();await page.getByRole('button',{name:'模型连接',exact:true}).click();
 const card=page.getByRole('region',{name:'Zotero 文献库连接'});await expect(card).toContainText('未测试');expect(tests).toBe(0);
 await card.getByRole('checkbox',{name:/启用/}).check();await card.getByLabel('连接模式').selectOption('remote');await card.getByLabel('远程 MCP 端点（URL）').fill('https://example.com/mcp');await card.getByLabel(/访问令牌（可选/).fill(secret);await card.getByRole('button',{name:'保存 Zotero 设置'}).click();
 await expect(card.getByLabel(/访问令牌（可选/)).toHaveValue('');await expect(card).not.toContainText(secret);expect(tests).toBe(0);
 await card.getByRole('button',{name:'测试连接',exact:true}).click();await expect(card).toContainText('已连接');expect(tests).toBe(1);
 await card.getByRole('button',{name:'测试连接',exact:true}).click();await expect(card).toContainText('连接状态：连接失败');
});
