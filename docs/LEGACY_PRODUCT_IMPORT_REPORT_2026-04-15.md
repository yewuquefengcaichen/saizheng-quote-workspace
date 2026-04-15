# legacy 商品导入报告（2026-04-15）

## 概要

本次导入的目标是把 legacy 商品库 `data/products.json` 的核心数据迁入 **V2 PostgreSQL 商品域模型**。

导入后，V2 已可承接：

- 商品主档
- 分类 / 品牌 / 供应商
- SKU / 变体
- 商品图片元数据
- 后续图搜图与向量检索能力

---

## 1. 导入来源

- `data/products.json`

---

## 2. 导入结果

本次已落地到 PostgreSQL 的数量如下：

- 品牌：**54**
- 分类：**104**
- 供应商：**9**
- 商品：**5886**
- SKU / 变体：**5886**
- 商品图片：**25755**

---

## 3. 结构结论

当前 V2 的商品结构采用：

- `products`：商品主表
- `product_variants`：SKU / 规格层
- `product_images`：商品图片关联
- `image_assets`：图片归档资产层
- `image_embeddings`：图片特征 / 向量层

也就是说，legacy 里“一条商品记录塞很多字段”的方式，已经开始拆成更可维护的结构。

---

## 4. 导入价值

这一步的价值不是“把 JSON 换个地方放”，而是把后续关键能力的底层铺好：

1. 商品库列表页改为优先走 PostgreSQL
2. 报价项人工搜索优先走 PostgreSQL
3. 商品详情优先走 PostgreSQL
4. 图搜图直接依赖图片资产与向量表
5. 后续可继续接商城同步 / 抓取

---

## 5. 下一步建议

- 继续减少 legacy JSON 读取路径
- 把新商品同步也统一落到 PostgreSQL
- 保留 `data/products.json` 作为过渡期回退源，不再作为长期主存储
