# ShopFlow

在现有项目中接入了 DeepSeek 的工具决策循环。真实模型能够选择搜索、读取商品依据、修改约束与方案，并读取工具返回继续决策。当前仍是有已知失败案例的本地原型，**不是完整交易闭环**。

## 运行

需要 Python 3.11+；服务不需要第三方包。当前本机已配置密钥，直接运行：

```powershell
python server.py
```

打开 http://127.0.0.1:8765 。配置修改后重启。SQLite 保存任务与偏好，同一浏览器会话可恢复；不要删除 data/shopping.sqlite3。首页仅一个示例，默认真实资料。原有演练目录与用户任务保留。

## 模型配置

首次安装复制 .env.example 为 .env，只在本机编辑。真正需要填写的是 LLM_API_KEY；当前供应商已确定为 DeepSeek，其余已给出：

| 变量 | 当前选项 |
|---|---|
| AGENT_MODE | live；独立规则模式为 offline |
| LLM_PROVIDER | deepseek |
| LLM_BASE_URL | https://api.deepseek.com |
| LLM_MODEL | deepseek-v4-flash |
| LLM_THINKING | disabled |
| LLM_PROMPT_VERSION | live-improved；baseline 文件独立保留 |
| LLM_BUDGET_ID | 本机持久预算标识 |
| LLM_PRICE_DATE | 2026-09-08，估算价格版本 |

密钥不进入浏览器或报告，.env 和数据库被 git 忽略。使用官方 Chat Completions function tools、非流式、显式关闭思考模式；不依赖 strict schema 或假定其他兼容供应商也支持。[官方接口](https://api-docs.deepseek.com/api/create-chat-completion/)、[思考模式](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/)、[核对费率](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)。

接口失败、未配置、循环超限均如实失败，原方案保留，不静默切换规则模式。每轮最多 8 次请求、20 次工具执行、150 秒、最多 1 次重试；请求全文不超过 60,000 UTF-8 字节，输出不超过 2,000 tokens。评测每轮请求上限为 5，计入最终回复。

## 费用与调用上限

本次先授权40次，再追加40次；共75/80次，剩余5次。75次供应商 usage 估算约 **¥0.1684643**，不等于账单。初始协议探测3次另计约¥0.001173，2次失败探测费用未知。详见 [预算记录](reports/call-budget-summary.json)。

```powershell
python budget.py
```

首次新环境须自行决定调用额度后初始化，例如设置 LLM_BUDGET_ID=local-validation 并运行 `python budget.py --id local-validation --cap 40`。cap 为累计上限，修改它不会重置已用次数；不要在不打算增加费用时提高它。服务、协议探测、评测共用持久计数。调用预算可能在失败前被预留，审计同时保留实际请求事件；未知费用不是零。

## Bad case 复盘（2026-09-09）

[结构化复盘](docs/badcases.md)整理 8 个真实问题；`/evaluation` 支持优先查看仍失败与回归退步、逐案例版本记录和证据详情。本轮仅进行确定性修复与浏览器检查，新增模型请求为 0。系统测试 79/79、呈现测试 19/19，见 [本轮验证](reports/badcase-validation.json)。

候选策略 `live-bc-review` 尚未真实复测，未替换本机策略配置。L03 日志表明模型拒绝用测试资料规划演练，不能简单归因于普通追问策略；L02 已暂存方案后重复检查，耗尽最终回复机会。新工具金额/检索范围契约、终止调度和评测额度预检已做代码验证，不能据此宣称模型效果提升。面试材料独立存放于 `E:\实习\badcase-interview.md`。

## 上轮证据（历史保留）

- 真实资料 **24 型号 / 6 类**，测试样品 **10 个**单独保留。14个真实型号有已提取的官方图片直链，其他显示缺图。中国市场规划价格、库存、配送均未知，4个美国官方参考报价单独以USD记录，不混算。[来源清单](docs/product-sources.md)。
- 浏览器验证了1000元桌面需求、必要讨论、键盘/台灯搜索与方案、修改600元及排除显示器、显式确认、外部Logitech商品页跳转；台灯只提供资料。另验证K120单品、保存恢复、确认失效、故障保留方案、桌面和窄屏。[浏览器记录](reports/browser-verification.json)。
- 当前系统 **68/68**、呈现 **19/19**；离线规则 v1 **30/32**、v2 **32/32**，和真实模型分开。
- 真实模型首批：3通过、2失败、3未运行；补批4/4（包含重跑资源不足的L05）。L02改进复测通过；L03回归退步；L04仍通过。**没有总体提升结论**，没有把规则成绩改名为真实模型成绩。[逐批报告与bad case](docs/live-evaluation.md)。
- Shopify、可信订单回传、真实支付均未接通。仅保留本地结算演练与核实来源的外部链接。真实外部动态搜索未接入；主动发现使用本地可追溯资料库。

## 验证与复现

```powershell
python verify.py
python evaluate.py --mode offline
python integrations.py check
```

verify.py 独立记录测试开始/结束时间和文件摘要，强制离线测试，不消耗 API。离线评测追加时间戳报告，不覆盖历史 reports/evaluation.json。当前验证见 reports/live-verification.json；旧52/52、18/18报告继续保存为历史快照。

以下命令会消耗 API，先检查剩余额度并决定预算：

```powershell
python protocol_smoke.py
python evaluate_live.py --prompt live-baseline --ids L01 --max-calls 5
```

固定模型集在 eval/live-cases.json；固定数据快照在 reports/snapshots/。报告追加到 reports/live-eval-*.json，可在 /evaluation 查看原始批次与逐案例轨迹。/runs 仅显示当前会话的运行；日志包含工具输入摘要、实际结果、耗时、版本、断言、重试与 usage，不保存供应商私有 reasoning 字段。

本地故障实验室需 ENABLE_TEST_LAB=1 后重启；故障注入明确标记为夹具。默认关闭。更完整的完成边界见 [验收状态](docs/acceptance.md)。
