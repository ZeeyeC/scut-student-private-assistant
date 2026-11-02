第三轮803后台+20子项、114前端通过；110界面通过，真实扩展用例一项失败，候选未发布。诊断发现真实学校tab已有id，但chrome.tabs.query未暴露url/pendingUrl，旧URL筛选无法到达其已有about:blank附着逻辑。按扩展真实session绑定id附着，旁观真实tabs.create参数及返回id（调用真实API，不替换tab/结果），保留初始学校入口断言、同id导航、真实content script回传及合成课程原文断言。Chrome权限行为参考https://developer.chrome.com/docs/extensions/reference/api/tabs#permissions；未扩大产品扩展权限。

修正后完整真实扩展流程连续五轮通过；独立复核无Important。API旁观层保留真实函数、参数及返回值，不替代真实创建/抓取/回传。随后仍执行最终完整发布门禁。
