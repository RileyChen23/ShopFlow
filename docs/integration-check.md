# 外部集成核实

核实于 2026-09-07；实现与本地验收延续至 2026-09-08。只检查环境变量是否存在，没有打印密钥值。没有购买付费套餐、充值、创建账户或真实商品交易。

| 服务 | 已核实与实测 | 状态 / 最少配置 |
| --- | --- | --- |
| 模型 | 阅读官方工具调用文档；本地适配器合同测试覆盖工具往返、错误工具拒绝、未知 usage；实际 model-smoke 因缺配置未发送请求 | 未完成。LLM_API_KEY、LLM_MODEL、LLM_BASE_URL；服务端填写，先跑 1 例 |
| 商品发现 | 官方页面读取成功：A24i、K380s、Mouse 2、挂灯；字段与摘录保存在 catalog.json | 可读规格，非中国市场实时价格/库存；当前只有 4 型号，不是 30—50 型号 |
| Shopify Cart | 官方文档核实 cartCreate、merchandiseId、quantity、checkoutUrl；实现请求与返回核对 | 未完成。无店铺、token、测试 SKU，未创建外部购物车，未取得外部结算 URL |
| 本地结算 | 实际 HTTP 和浏览器：确认 → 购物车 → 本地演练页 | 已运行；纯模拟，不是 Shopify，不产生付款或订单 |
| 外部商品页 | K380s 英国官方商品页可读取 | 仅是外部购买入口，不是结算链接；GBP，布局与配送中国未知 |

## 模型来源与费用

[OpenAI Function calling](https://developers.openai.com/api/docs/guides/function-calling) 说明模型提出工具调用，由应用执行并回传结果。本项目选择兼容 Chat Completions 的函数工具接口；这不证明任意兼容供应商都支持相同字段。

价格由供应商与所选模型决定。模型尚未指定，不能给出真实费用。默认单轮 5 次请求、每输出 1200 tokens，日限 50 请求，批评测限 3 案例；可显式修改。费率通过环境变量人工配置并标记来源/日期；费用仅估算。没有自动重试/自动充值。

## Shopify 资格与支付条件

[Dev stores](https://shopify.dev/docs/apps/build/stores/development-stores)：需要 Partner 账户或具有开发权限的商家账户及组织相应权限。开发店铺用于测试，不能处理真实交易，支持 Bogus gateway 或支付供应商测试模式，存在密码页和生产/转移限制。

[Cart 管理官方文档](https://shopify.dev/docs/storefronts/headless/building-with-the-storefront-api/cart/manage)：购物车包含具体变体和数量，通过 API 获取结算 URL；成本仍会在结算时变化。cart ID 中的 secret 不能公开。本实现不把 Shopify cart ID 返回前端或日志。

开发店铺与自有应用测试条件以账户后台为准；本次未登录，无法核实用户具体资格或账单。未选购任何商家付费方案。即使文档允许测试，也不能在缺少账户时宣称已有免费可用店铺。

最少操作：准备开发测试店铺，启用支付测试模式；创建 1—2 个 TEST- SKU、CNY 价格；填写 .env；运行 shopify-import；重启后在页面手动确认并创建购物车。环境变量 ACK 是操作者确认，不是独立证明支付配置；使用前必须在后台核实。

## 商品来源清单

- [A24i 规格](https://www.mi.com/global/product/xiaomi-monitor-a24i/specs/)：型号、分辨率、尺寸、DP/HDMI。未取得售价或购物链接。
- [K380s 英国商品页](https://www.logitech.com/en-gb/shop/p/pebble-keys-2.920-011821)：蓝牙、安静低键程按键、设备切换。读取到的促销与具体选项/可售性不足以证明当前报价，故保存售价未知，不沿用促销数字。
- [Mouse 2 FAQ](https://www.mi.com/global/support/faq/details/KA-497422/)：双模、DPI、USB-A 与 macOS 侧键限制。FAQ 不是购买链接。
- [挂灯官方页](https://www.mi.com/global/product/mi-computer-monitor-light-bar/)：安装厚度与不建议笔记本使用。图源保留在 image_source，未把生成图片当实物。

旧 K380 地址被重定向到键盘分类页，未收录为该型号购买入口。真实商品与演练样品完全分开。没有授权的商品数据源/店铺价格接口，故不虚构中国市场价格、优惠与库存。搜索范围仅为这些已导入资料，不提供全网最低价或实时网页搜索。
