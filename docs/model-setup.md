# 模型与搜索配置

复制 `.env.example` 为 `.env`，在服务端填写两项密钥：

```dotenv
LLM_API_KEY=your_deepseek_key
SEARCH_API_KEY=your_tavily_key
```

`.env` 已被 Git 忽略。密钥只用于服务端请求，不会发送到浏览器或写入运行报告。修改配置后需要重启 `python server.py`。

## DeepSeek

默认使用 `deepseek-flash` 和 Chat Completions function tools。适配层使用非流式响应、关闭思考模式，并在执行每个工具前进行服务端 schema 校验。可用模型名称应以当前账号的 `/models` 返回为准。

- [接口参考](https://api-docs.deepseek.com/api/create-chat-completion/)
- [工具与思考模式](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/)
- [模型费率](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

模型请求受单轮请求数、工具数、超时、每日额度和本机累计额度共同限制。可使用 `python budget.py` 查看累计额度，或在首次运行时执行：

```powershell
python budget.py --id local-validation --cap 40
```

## Tavily Search

正式任务的 `search_products` 默认调用 Tavily Search API。基础搜索返回标题、来源 URL、相关摘要和请求 ID；ShopFlow 将结果转换为任务级的 `product / variant / offer / evidence` 快照。

- [Search API 参考](https://docs.tavily.com/documentation/api-reference/endpoint/search)
- [API 与认证说明](https://docs.tavily.com/documentation/api-reference/introduction)

相关配置：

```dotenv
SEARCH_PROVIDER=tavily
SEARCH_BASE_URL=https://api.tavily.com/search
SEARCH_TIMEOUT_SECONDS=15
SEARCH_MAX_RESULTS=5
```

通用搜索摘要没有结构化价格时，`price_minor` 保持为 `null`。ShopFlow 不从摘要推测价格，也不会把空结果解释为市场上没有商品。

## 演练模式

设置 `AGENT_MODE=offline` 可运行规则演练。`scope=demo` 使用本地测试目录；正式范围的商品发现仍依赖外部 Search Provider。两种结果通过数据类型和任务范围隔离。
