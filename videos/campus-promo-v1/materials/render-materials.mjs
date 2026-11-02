import {chromium} from '../../../frontend/node_modules/playwright/index.mjs';
import {fileURLToPath, pathToFileURL} from 'node:url';
import path from 'node:path';
import os from 'node:os';
const dir=path.dirname(fileURLToPath(import.meta.url));
const browser=await chromium.launch({headless:true,executablePath:path.join(os.homedir(),'Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing')});
try {
 const page=await browser.newPage({viewport:{width:1100,height:1500},deviceScaleFactor:1});
 await page.goto(pathToFileURL(path.join(dir,'作业通知.html')).href);
 await page.evaluate(()=>document.fonts.ready);
 await page.locator('body').screenshot({path:path.join(dir,'作业通知.png')});
 await page.goto(pathToFileURL(path.join(dir,'讲义.html')).href);
 await page.evaluate(()=>document.fonts.ready);
 await page.pdf({path:path.join(dir,'微积分-导数应用练习.pdf'),preferCSSPageSize:true,printBackground:true});
 console.log('Rendered fictional notice and one-page lecture.');
}finally{await browser.close();}
