# ShopFlow

ShopFlow 是一个面向宿舍、居家学习与办公场景的 AI 采购助手。用户可以直接描述目标、预算和已有物品，ShopFlow 会检索可追溯的商品资料，比较规格与价格，并把建议整理成一份可继续修改的采购方案。

项目将对话、方案与任务状态连接在一起：模型根据当前需求选择工具，读取真实工具结果后继续决策；预算、数量、兼容性和购买确认由服务端校验。用户可以在对话中降低预算、删除条目或补充限制，页面上的方案会同步更新。

## 主要能力

- 根据用途、预算、已有物品和排除条件搜索商品
- 读取品牌型号、规格、报价时间和来源链接
- 生成单品或组合采购方案，并计算已知费用与预算余额
- 在后续对话中修改预算、数量和方案条目
- 保存任务，在同一浏览器中恢复进度
- 用户确认后生成本地结算演练入口或外部商品入口
- 查看模型请求、工具调用、状态变化和评测结果

## 产品结构

ShopFlow 包含三个主要页面：

- **采购工作台**：完成需求沟通、商品选择和方案调整
- **运行记录**：查看一次任务中的模型请求、工具调用、耗时和状态变化
- **评测与迭代**：查看系统测试、规则回归、真实模型案例和 bad case 复盘

商品资料分为真实资料与演练资料。真实模式默认检索经过整理的公开商品资料；演练模式使用独立测试目录，适合验证预算、状态和结算流程。

## 快速开始

环境要求：Python 3.11+。应用服务使用 Python 标准库，无需安装额外的 Python 依赖。

```powershell
git clone https://github.com/RileyChen23/ShopFlow.git
cd ShopFlow
Copy-Item .env.example .env
```

在 `.env` 中填写 DeepSeek API 密钥：

```dotenv
LLM_API_KEY=your_api_key
```

初始化本机调用额度并启动服务：

```powershell
python budget.py --id local-validation --cap 40
python server.py
```

打开 [http://127.0.0.1:8765](http://127.0.0.1:8765)。任务和偏好保存在本地 SQLite 数据库中。

## 模型与工具循环

当前适配 DeepSeek Chat Completions function tools，默认模型配置为 `deepseek-v4-flash`。一次对话的执行过程是：

1. 服务端向模型提供用户输入、当前任务状态和可用工具。
2. 模型选择追问、调用工具或生成结果。
3. 服务端验证工具参数，执行商品搜索、资料读取或方案更新。
4. 工具结果返回模型，模型据此继续决策或回复用户。
5. 经过校验的结果写入当前任务，页面同步展示最新方案。

可用工具覆盖商品搜索、商品依据读取、任务状态读取、预算与约束修改、方案更新及兼容性检查。购买确认独立于模型工具调用，由用户在界面中完成。

主要配置项：

| 变量 | 用途 | 默认值 |
|---|---|---|
| `AGENT_MODE` | `live` 使用真实模型，`offline` 使用规则演练 | `live` |
| `LLM_BASE_URL` | 模型 API 地址 | `https://api.deepseek.com` |
| `LLM_MODEL` | 模型名称 | `deepseek-v4-flash` |
| `LLM_PROMPT_VERSION` | 当前提示策略 | `shopflow` |
| `LLM_BUDGET_ID` | 本机持久调用额度标识 | `local-validation` |
| `LLM_MAX_CALLS` | 单轮模型请求上限 | `8` |
| `LLM_MAX_TOOLS` | 单轮工具调用上限 | `20` |

完整配置见 [.env.example](.env.example)，模型接入说明见 [docs/model-setup.md](docs/model-setup.md)。

## 商品资料

当前资料库覆盖显示器、键盘、台灯、耳机、扩展坞和笔记本支架等学习办公品类。每条资料分别记录型号、规格、来源、采集日期、图片来源与报价信息；未知价格、库存或配送状态保持为未知。

真实资料与测试样品使用独立标识和检索范围。商品来源与覆盖情况见 [docs/product-sources.md](docs/product-sources.md)。

## 测试与评测

运行系统测试：

```powershell
python -m unittest discover -s tests -v
node --test tests/maintenance-data.test.cjs
```

运行离线规则评测：

```powershell
python evaluate.py --mode offline
```

运行指定真实模型案例：

```powershell
python evaluate_live.py --prompt shopflow --ids L01 --max-calls 5
```

真实模型评测会使用 `.env` 中配置的 API 和本机调用额度。固定案例位于 [eval/live-cases.json](eval/live-cases.json)，运行报告保存在 `reports/`，并可在应用的“评测与迭代”页面查看。

项目保留了真实运行中发现的问题及修复证据，便于按需求理解、工具调用、数据、状态和回复生成等环节定位问题。详见 [Bad case 复盘](docs/badcases.md) 和 [真实模型评测记录](docs/live-evaluation.md)。

## 当前范围

ShopFlow 目前提供本地采购规划、结算演练和已核实的外部商品链接。商品发现基于项目内的可追溯资料库，尚未接入实时全网比价、Shopify 订单回传或在线支付。

## 项目文档

- [产品说明](docs/product.md)
- [实现结构](docs/implementation-plan.md)
- [商品来源](docs/product-sources.md)
- [模型配置](docs/model-setup.md)
- [评测说明](docs/evaluation.md)
- [Bad case 复盘](docs/badcases.md)
