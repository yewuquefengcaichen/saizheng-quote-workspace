# 旧数据盘点（2026-04-15）

这份盘点是为 PostgreSQL 迁移做准备，结论只基于当前仓库里的实际数据文件。

---

## 1. 商品库：`data/products.json`

- 文件大小：约 **9.26 MB**
- 记录数：**5886**
- 当前结构：**list[dict]**
- 首批字段：
  - `code`
  - `name`
  - `model`
  - `category`
  - `unit`
  - `market_price`
  - `cost_price`
  - `brand`
  - `supplier`
  - `status`
  - `intro`

### 数据特点

- 品牌数：**54**
- 供应商数：**9**
- 类目路径数：**89**
- 状态分布：
  - `上架`：**5242**
  - `下架`：**644**
- `model` 为空：**732**
- `cost_price > 0`：**0**
- `intro` 非空：**2240**

### 当前判断

这个 JSON 更像是**商品行级数据**，但它没有明确给出：

- SPU / SKU 拆分
- 图片数组
- 结构化属性表

所以迁移第一版建议采用：

> **一条 legacy 行 = 一个 product + 一个 product_variant**

等后面商城同步能力接进来，再做更细颗粒度的 SPU / SKU 重构。

---

## 2. 报价历史：`data/quote_history.db`

- 文件大小：约 **0.07 MB**

### 表结构与数量

#### `match_feedback`

- 数量：**86**
- 字段：
  - `id`
  - `created_at`
  - `source_type`
  - `template_name`
  - `template_hit`
  - `action`
  - `original_name`
  - `original_spec`
  - `original_unit`
  - `normalized_name`
  - `normalized_spec`
  - `normalized_unit`
  - `selected_product_code`
  - `selected_product_name`
  - `top_candidate_code`
  - `top_candidate_name`
  - `top_candidate_score`
  - `top_candidate_rank`
  - `selected_rank`
  - `selected_score`
  - `with_product_image`
  - `ocr_confidence`
  - `query_signature`
  - `feedback_weight`
  - `mapping_signature`
  - `mapping_changed`

#### `quote_history`

- 数量：**1**
- 字段：
  - `id`
  - `created_at`
  - `customer_name`
  - `quote_file`
  - `total_items`
  - `matched_items`
  - `total_amount`
  - `export_file`
  - `remark`

#### `quote_items`

- 数量：**19**
- 字段：
  - `id`
  - `quote_id`
  - `item_name`
  - `item_quantity`
  - `item_unit`
  - `item_price`
  - `budget_price`
  - `product_name`
  - `product_code`
  - `supplier`
  - `match_score`

### 当前判断

历史报价数据量目前不大，迁移复杂度低。  
优先级上可以放在商品库迁移之后。

---

## 3. AI 缓存：`data/ai_cache.db`

- 文件大小：约 **0.02 MB**

### 表结构与数量

#### `embeddings`

- 数量：**0**
- 字段：
  - `id`
  - `text_hash`
  - `text`
  - `embedding`
  - `created_at`

#### `responses`

- 数量：**0**
- 字段：
  - `id`
  - `prompt_hash`
  - `prompt`
  - `response`
  - `created_at`

### 当前判断

现在这个库基本是空的。  
后面可以不急着迁，先决定：

- 是继续保留 SQLite 缓存
- 还是迁到 PostgreSQL / Redis
- 或者直接重做成新的缓存层

---

## 4. 规则类 JSON

### `data/synonyms.json`

- 类型：`dict`
- 典型键：`袖套`、`手套`、`安全帽`、`口罩`、`劳保鞋`

### `data/parse_templates.json`

- 类型：`dict`
- 顶层键：`templates`

### `data/normalization_rules.json`

- 类型：`dict`
- 顶层键：
  - `name_aliases`
  - `unit_mappings`
  - `spec_patterns`

### 当前判断

这些数据非常适合逐步入 PostgreSQL：

- `synonyms`
- `parse_templates`
- `normalization_rules`

但保留 JSON 作为种子数据/导出备份仍然有价值。

---

## 5. 迁移顺序建议

1. 先迁 `products.json`
2. 再迁 `quote_history.db`
3. 再迁规则类 JSON
4. 最后再决定 `ai_cache.db` 的去留

---

## 6. 当前已做的铺垫

- V2 后端骨架已建立
- 首批核心表已建立
- 可以开始写真正的导入脚本
- `backend/scripts/import_legacy_products.py` 已作为第一版商品迁移脚本骨架落地
