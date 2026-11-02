"""Create original fictional teaching content. Never reads personal data."""
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import json

root = Path(__file__).resolve().parent
today = datetime.now(ZoneInfo('Asia/Shanghai')).date()
monday = today - timedelta(days=today.weekday())
due = today + timedelta(days=3)
notice = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>虚构作业通知</title>
<style>
@font-face{{font-family:Demo;src:url('file:///Library/Fonts/NotoSansCJKsc-Regular.otf')}}
*{{box-sizing:border-box}}body{{margin:0;width:1100px;background:#f2f4fa;padding:62px;font-family:Demo,sans-serif;color:#272d3e}}article{{background:white;padding:60px;border:1px solid #e2e6f1;border-radius:28px}}.eyebrow{{font-size:19px;color:#6571a0;letter-spacing:3px}}h1{{font-size:46px;margin:18px 0 12px;letter-spacing:1px}}.sub{{font-size:22px;color:#7a8193;margin-bottom:44px}}section{{border-top:1px solid #e4e7ef;padding:32px 0 12px}}h2{{font-size:28px;margin:0 0 20px}}p{{font-size:25px;line-height:1.9;margin:8px 0}}.tag{{display:inline-block;border-radius:8px;padding:6px 12px;background:#eff0fc;color:#6668bd;font-size:17px;margin-bottom:12px}}footer{{margin-top:32px;color:#8a91a2;font-size:18px}}
</style><article><div class="eyebrow">课程通知 · 虚构演示</div><h1>本周课后练习</h1><div class="sub">发布日期：{today:%Y年%m月%d日}</div>
<section><div class="tag">微积分</div><h2>导数应用练习</h2><p>完成练习讲义中的第 1–4 题，写出求导过程。<br>预计用时 25 分钟。<br>截止：{due:%Y年%m月%d日} 20:00。</p></section>
<section><div class="tag">学术英语</div><h2>准备两分钟英文自我介绍</h2><p>整理一份英文提纲，并进行一次口头练习。<br>预计用时 25 分钟。<br>截止日期另行通知。</p></section>
<footer>原创虚构通知，仅用于课间产品演示。</footer></article></html>'''
(root/'作业通知.html').write_text(notice)
lecture = '''# 微积分 · 导数应用练习

原创虚构课程讲义 / 产品演示样例

## 1. 本节要点

导数描述函数在某一点附近的瞬时变化率。求解多项式的导数时，可以先逐项求导，再合并结果。

幂函数求导：当 n 是正整数时，f(x) = x^n 的导数为 f'(x) = n x^(n-1)。常数的导数为 0。

## 2. 示例

设 f(x) = x^3 - 2x + 1。

逐项求导得到 f'(x) = 3x^2 - 2。当 x = 2 时，f'(2) = 10。

这里的 10 表示该点处切线的斜率。计算前应先求出导函数，再代入指定的 x 值。

## 3. 课后练习

1. 求 f(x) = x^2 + 3x 的导数。
2. 求 f(x) = 2x^3 - x^2 + 4 的导数。
3. 对 f(x) = x^3 - 2x + 1，计算 x = 2 时的导数。
4. 用一句话解释导数值的几何意义。

请写出关键步骤。建议先独立练习 25 分钟，再核对结果。

本文不包含真实学校、教师或学生资料；内容为原创基础数学示例。
'''
(root/'微积分-导数应用练习.md').write_text(lecture)
sections=''.join('<h2>'+s.split('\n',1)[0]+'</h2><p>'+s.split('\n',1)[1].strip().replace('\n\n','</p><p>').replace('\n','<br>')+'</p>' for s in lecture.split('## ')[1:])
(root/'讲义.html').write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>微积分 · 导数应用练习</title><style>@font-face{font-family:Demo;src:url('file:///Library/Fonts/NotoSansCJKsc-Regular.otf')}@page{size:A4;margin:20mm}body{font-family:Demo,sans-serif;color:#2b3041;font-size:12px;line-height:1.85}header{font-size:10px;color:#747c9a;letter-spacing:2px}h1{font-size:27px;margin:16px 0 25px}h2{font-size:17px;margin:24px 0 10px;color:#5f64a4}p{margin:8px 0}footer{margin-top:26px;border-top:1px solid #e0e4ef;padding-top:10px;font-size:10px;color:#8b91a2}</style><header>课间 / 原创虚构课程资料</header><h1>微积分 · 导数应用练习</h1>'''+sections+'<footer>虚构演示样例 · 1</footer></html>')
manifest={
  'fictional':True,'generated_date':str(today),'timezone':'Asia/Shanghai',
  'semester_week1_monday':str(monday),'due':f'{due}T20:00:00+08:00',
  'courses':[
    {'source_key':'promo-calculus','name':'微积分','weekday':1,'weeks':list(range(1,19)),'periods':[1,2],'location':'示例楼 A101'},
    {'source_key':'promo-english','name':'学术英语','weekday':3,'weeks':list(range(1,19)),'periods':[3,4],'location':'示例楼 B203'},
    {'source_key':'promo-programming','name':'程序设计','weekday':5,'weeks':list(range(1,19)),'periods':[5,6],'location':'示例楼 C302'}],
  'expected_tasks':[
    {'title':'导数应用练习','course':'微积分','duration_minutes':25,'due':f'{due}T20:00:00+08:00'},
    {'title':'准备两分钟英文自我介绍','course':'学术英语','duration_minutes':25,'due':None}],
  'unconfirmed_preference':'我希望每次专注25分钟。',
  'knowledge_question':'请根据这份讲义，解释怎样求 f(x)=x³−2x+1 在 x=2 时的导数。',
  'expected_knowledge_answer':'先逐项求导得到 3x²−2，再代入 x=2，结果为10；对应讲义第2节。',
  'provenance':'课程、教室、通知与讲义均为本轮原创虚构内容，不取自个人资料。'}
(root/'fictional-data.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'date':str(today),'due':str(due),'files':4},ensure_ascii=False))
