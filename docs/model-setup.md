# DeepSeek 本机配置

本机已填密钥，不要把它发到聊天、截图或前端。更换密钥仅编辑根目录 .env 中 LLM_API_KEY=，保存后重启 python server.py。

模型选择 deepseek-v4-flash，地址 https://api.deepseek.com，LLM_PROVIDER=deepseek。已按官方接口核对 function tools；本适配器明确 thinking.disabled、stream=false，不启用strict，不假定其他兼容接口相同。服务端参数校验始终执行。

官方资料核对日期2026-09-08：
- [接口参考](https://api-docs.deepseek.com/api/create-chat-completion/)
- [工具与思考模式](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/)
- [CNY费率与高低峰](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

费率使用 cache-hit / cache-miss / output usage，缺字段则未知；本机保存价格日期和来源。工作日北京时间9–12、14–18为所核对的高峰费率，其余为低峰。估算不是供应商实际扣款账单，若官方规则变动应先更新provider.py和价格日期，再授权评测。

日限额和累计限额都生效。当前累计75/80，重启不会清零。用 python budget.py 只读检查；仅在明确接受相应费用后用 --cap 设置新的累计上限。达到限额后不发送请求，不降级成规则并显示成功。

规则演练是独立配置 AGENT_MODE=offline；商品演练目录是独立 scope=demo。真实模型可以使用固定测试目录做可重复评测，但这不意味着测试价格是真实行情。
