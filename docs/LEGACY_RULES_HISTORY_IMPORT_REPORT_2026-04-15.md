# legacy 规则与历史迁移报告（2026-04-15）

## 概要

本次迁移把 legacy 的规则、模板、历史与反馈数据迁入 PostgreSQL，目的是为后续新架构保留“历史学习能力”和“可追溯性”。

---

## 1. 迁移来源

- `data/synonyms.json`
- `data/normalization_rules.json`
- `data/parse_templates.json`
- `data/quote_history.db`

---

## 2. 当前结果

已落地到 PostgreSQL 的数据量如下：

- `synonyms`：**84**
- `normalization_rules`：**25**
- `parse_templates`：**5**
- `quote_batches`：**1**
- `quote_items`：**19**
- `match_feedback`：**83**

---

## 3. 迁移意义

### 同义词 / 规范化规则

迁移后可以继续支撑：

- 名称归一化
- 规格归一化
- 商品搜索增强
- 报价项匹配纠偏

### 解析模板

迁移后模板不再只靠 JSON 存放，后续可以：

- 做版本管理
- 做多来源模板
- 做模板命中统计
- 做模板回溯与人工修正

### 历史 / 反馈

迁移后可以保留：

- 旧报价批次
- 报价项明细
- 人工确认反馈
- 后续学习信号

---

## 4. 当前结论

V2 现在已经不只是“商品进库”，而是：

- 商品域进 PostgreSQL
- 规则域进 PostgreSQL
- 历史 / 反馈进 PostgreSQL

这意味着后续无论是做新前端、任务队列、缓存还是 AI 增强，都已经有了统一数据底座。
