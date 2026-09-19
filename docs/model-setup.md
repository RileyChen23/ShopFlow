# 模型与搜索配置

复制 `.env.example` 为 `.env`，在服务端填写两项密钥：

```dotenv
LLM_API_KEY=your_deepseek_key
RAINFOREST_API_KEY=your_rainforest_key
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

## Rainforest Product Search

正式任务的 `search_products` 默认调用 Rainforest Product Data API。基础搜索返回 Amazon 商品的 ASIN、标题、链接、图片和可用报价；ShopFlow 将结果转换为任务级的 `product / variant / offer / evidence` 快照。

- [Search 参数](https://docs.trajectdata.com/rainforestapi/product-data-api/parameters/search)
- [通用参数与认证](https://docs.trajectdata.com/rainforestapi/product-data-api/parameters/common)

相关配置：

```dotenv
SEARCH_PROVIDER=rainforest
RAINFOREST_BASE_URL=https://api.rainforestapi.com/request
RAINFOREST_API_KEY=your_key
RAINFOREST_AMAZON_DOMAIN=amazon.com
RAINFOREST_CUSTOMER_LOCATION=
SEARCH_TIMEOUT_SECONDS=20
SEARCH_MAX_RESULTS=5
```

通用搜索摘要没有结构化价格时，`price_minor` 保持为 `null`。ShopFlow 不从摘要推测价格，也不会把空结果解释为市场上没有商品。

## 演练模式

设置 `AGENT_MODE=offline` 可运行规则演练。`scope=demo` 使用本地测试目录；正式范围的商品发现仍依赖外部 Search Provider。两种结果通过数据类型和任务范围隔离。
