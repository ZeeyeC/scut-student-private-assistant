课间2.7新增组件：MarkItDown(MIT)、MCP Server Fetch(MIT)、Qdrant Client(Apache-2.0)、FastEmbed(Apache-2.0)、ONNX Runtime(MIT)、Tokenizers(Apache-2.0)、Magika(Apache-2.0)。锁定版本见backend/uv.lock。FastEmbed模型BAAI/bge-small-zh-v1.5按需下载，不在App中包含权重，模型许可MIT。组件代码/模型许可分别保留。
https://github.com/microsoft/markitdown
https://github.com/modelcontextprotocol/servers
https://github.com/qdrant/qdrant-client
https://github.com/qdrant/fastembed
https://github.com/microsoft/onnxruntime
https://github.com/huggingface/tokenizers
https://github.com/google/magika
https://huggingface.co/BAAI/bge-small-zh-v1.5

2.8新增Zotero MCP Server0.15.2（MIT及随附插件AGPL许可分别保留，App仅运行只读Python服务，不安装上游Zotero插件）、FastMCP3.4.11、Pyzotero1.14.0、pdf-inspector0.2.6。没有引入Chroma或Torch，不自动读取其他助手配置/本机Zotero SQLite，不运行索引自动更新。上游原代码及许可来源https://github.com/54yyyu/zotero-mcp；依赖版本以backend/uv.lock为准。
