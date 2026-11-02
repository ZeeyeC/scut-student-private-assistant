# Demo2.9.1 检索设置排版修复

“启用语义检索”的文字移到复选框右侧，保持垂直居中；窄窗口下准备按钮可自然换行。仅调整此处样式，启用、禁用与手动下载确认逻辑不变。

## 如何获取搜索服务地址

当前接入 SearXNG 的 JSON 搜索接口。

- 自行部署：按 [官方 Docker 部署说明](https://docs.searxng.org/admin/installation-docker.html) 配置。本机部署并监听 8080 端口后，例如填写 `http://127.0.0.1:8080`；这只是示例，不代表本机已经运行该服务。
- 使用公开服务：在 [公开实例列表](https://searx.space/) 选择允许 JSON 请求的实例，再在 App 中保存地址并测试连接。许多公开实例关闭 JSON 格式，需要逐个确认。

服务端 `settings.yml` 的 `search.formats` 必须包含 `json`，否则返回 403，见 [官方搜索 API](https://docs.searxng.org/dev/search_api.html)。App 请求 `/search?q=…&format=json`；填写服务根地址或以 `/search` 结尾的地址即可，不附查询参数。远程服务使用 HTTPS，本机支持 HTTP。

本版不自动部署搜索服务，不自动下载语义模型，不调用付费模型。发布结果以本版验证记录与正式发布目录中的 manifest 为准。
