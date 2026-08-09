# AAPL 固定验收报告（脱敏 fixture）

> 本报告只用于离线 contract 回归。内容、编号和价格均为固定测试语料，不声明实时性，也不构成投资建议。

## 投资主线（thesis）

本 fixture 的基础情景假设是：AAPL 的设备生态、服务收入和资本回报共同支撑现金流韧性；该结论必须同时接受产品周期放缓与估值压缩的反证。

### 证据与出处

- filing-aapl-10k-2024 | 10-K / 0000320193-24-000123 | 2024-11-01 | Item 1 与 Item 8，业务分部及现金流量表

## Bear case 与反证

Bear case 假设硬件换机周期弱于预期、服务增长降速，并且高估值倍数回落。若未来季度收入组合和经营现金流同时恶化，基础情景失效。

### 证据与出处

- filing-aapl-10q-2025q1 | 10-Q / 0000320193-25-000008 | 2025-01-31 | Part I Item 2，季度经营讨论与分部趋势
- filing-aapl-10k-2024 | 10-K / 0000320193-24-000123 | 2024-11-01 | Item 1A，需求、供应链与监管风险

## 估值（valuation）

valuation_reference_price: {"price":"236.85","currency":"USD","market_date":"2025-01-15","material_document_id":"material-aapl-price-snapshot-2025-01-15"}

| 情景 | 固定验收假设 | 相对参考价判断 |
|---|---|---|
| Bear | 现金流承压且估值倍数收缩 | 下行 |
| Base | 现金流保持韧性且服务结构稳定 | 中性 |
| Bull | 产品周期与服务增长共同改善 | 上行 |

上述三种情景只是用于验证报告结构；没有把 fixture 价格解释为当前市场价格。

### 证据与出处

- material-aapl-price-snapshot-2025-01-15 | MATERIAL_OTHER / aapl-price-snapshot | 2025-01-15 | price=236.85 USD，market_date=2025-01-15
- filing-aapl-10k-2024 | 10-K / 0000320193-24-000123 | 2024-11-01 | Item 8，现金、债务、股本和现金流量表

## 催化剂（catalyst）

未来 6–18 个月的固定测试催化剂包括产品周期改善和服务变现增强；失效条件是披露数据不能支持相关增长或利润率改善。

### 证据与出处

- filing-aapl-10q-2025q1 | 10-Q / 0000320193-25-000008 | 2025-01-31 | Part I Item 2，管理层对季度经营驱动的讨论

## 风险（risk）

主要风险包括供应链集中、监管变化、产品需求波动和资本配置判断错误。管理层观点在本报告中仅作为观点，不替代财务报表事实。

### 证据与出处

- filing-aapl-10k-2024 | 10-K / 0000320193-24-000123 | 2024-11-01 | Item 1A，风险因素
- filing-aapl-def14a-2025 | DEF 14A / 0001308179-25-000008 | 2025-01-10 | 董事会监督与高管薪酬章节

## 来源清单

- filing-aapl-10k-2024 | 10-K / 0000320193-24-000123 | 2024-11-01 | Item 1、Item 1A 与 Item 8
- filing-aapl-10q-2025q1 | 10-Q / 0000320193-25-000008 | 2025-01-31 | Part I Item 2
- filing-aapl-def14a-2025 | DEF 14A / 0001308179-25-000008 | 2025-01-10 | 董事会监督与高管薪酬章节
- material-aapl-price-snapshot-2025-01-15 | MATERIAL_OTHER / aapl-price-snapshot | 2025-01-15 | 固定 price snapshot 六字段 material
