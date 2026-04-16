# 图搜图与 pgvector 进度报告（2026-04-15）

## 本轮结论

V2 已经从“只有图片归档与 hash”推进到“**有 pgvector、有图片向量、有以图搜图 API、有真实数据可查**”。

这意味着：

- 图片资产层已经不仅能存图
- 还能为后续拍照识别、相似商品召回、候选商品联动提供真实检索基础

---

## 本轮实际完成

1. 将 PostgreSQL 容器升级为支持 pgvector 的镜像
2. 在数据库中真实启用 `vector` 扩展
3. 为 `image_embeddings` 新增 `embedding_vector vector(128)`
4. 建立 HNSW 向量索引
5. 新增图片向量生成脚本
6. 真实生成 `3300` 条图片向量
7. 新增以图搜图 API
8. 新增图片归档文件访问接口

---

## 基础设施变化

### PostgreSQL 镜像

`docker-compose.v2.yml` 已从：

- `postgres:17-alpine`

升级为：

- `pgvector/pgvector:pg17`

### 升级前备份

在切换镜像前，已先导出一份数据库备份：

- `data/backups/saizheng_quote_v2_pre_pgvector_20260415_211353.sql`

### 扩展状态

已验证：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

当前数据库中已存在：

- `vector`

---

## 数据库结构变更

### Alembic 版本

当前版本已推进到：

- `20260415_0005`

### 新增内容

在 `image_embeddings` 中新增：

- `embedding_vector vector(128)`

并建立：

- `ix_image_embeddings_embedding_vector_hnsw`

当前保留双层结构：

- `embedding_vector`
  - 真正用于向量检索
- `embedding_json`
  - 保留可读调试信息（当前记录 `phash` / `dhash` 与策略说明）

---

## 当前 embedding 方案

### 当前落地方案

当前不是直接上 CLIP 大模型，而是先落一个**可运行、可验证、可无外部依赖部署**的本地方案：

- provider：`local_hash_embedding`
- model：`phash_dhash_128d_v1`
- 向量维度：`128`

### 向量来源

将：

- `phash` 64 bit
- `dhash` 64 bit

拼接为一个 128 维向量。

具体映射规则：

- bit=1 => `1.0`
- bit=0 => `-1.0`

### 为什么先这样做

这样做的优点：

- 不依赖外部 API
- 不依赖大模型 GPU
- 可以立刻落库并跑通图搜图全链路
- 后续升级到 CLIP / OpenAI / 自建视觉模型时，不需要推翻表结构与 API，只需要切换 provider/model 即可

也就是说：

> 现在做的是**第一版可运行向量底座**，不是最终上限，但架构方向是对的。

---

## 已新增代码

### 迁移

- `backend/alembic/versions/20260415_0005_enable_pgvector_and_add_embedding_vector.py`

### 服务

- `backend/app/services/image_embedding.py`

职责：

- `phash/dhash` => 128 维向量
- 上传图片 => 查询向量
- 向量检索相似商品
- 归档文件路径解析

### 脚本

- `backend/scripts/generate_image_embeddings.py`

用途：

- 从 `image_assets` 批量生成向量
- 写入 `image_embeddings`

### API

- `POST /api/v1/image-search/query`
- `GET /api/v1/image-search/assets/{asset_id}/file`
- `GET /api/v1/image-search/embedding-status`

---

## 已完成的真实数据结果

### 图片资产数

- `image_assets`：`3300`

### 已生成向量数

- `image_embeddings` ready：`3300`

### 扩展状态

- `vector` 扩展：已启用

### 查询验证

已用真实归档图片做一次检索验证：

- 查询资产：`asset_id=4`
- 检索结果 Top 1 命中同一资产
- 相似度：`1.000000`

说明：

- 向量写入正常
- 向量距离排序正常
- 以图搜图主链路已经能工作

---

## API 说明

### 1）图片检索

接口：

```text
POST /api/v1/image-search/query
```

请求方式：

- `multipart/form-data`
- 字段：
  - `file`: 上传图片文件
  - `top_k`: 返回条数，1~50

返回：

- 查询图片的 `phash` / `dhash`
- 当前 provider / model / vector_dim
- 候选商品列表
- 每个候选的：
  - `product_code`
  - `product_name`
  - `brand_name`
  - `similarity`
  - `distance`
  - `archive_file_url`
  - `storage_key`

### 2）图片资产文件访问

接口：

```text
GET /api/v1/image-search/assets/{asset_id}/file
```

用途：

- 前端可直接显示已归档图片
- 避免继续依赖旧商城远程图片链接

### 3）embedding provider 状态

接口：

```text
GET /api/v1/image-search/embedding-status
```

用途：

- 查看当前 `local_hash_embedding` 是否就绪
- 查看 `clip_local` 是否缺依赖
- 查看当前数据库向量列是否支持目标维度
- 为后续 CLIP / 更强视觉模型升级做预检

当前结论：

- `local_hash_embedding / phash_dhash_128d_v1`：可用，维度 128，当前数据库支持
- `clip_local / openclip_vit_b_32_512d`：预留，维度 512；需要安装 `torch / open_clip_torch`，并增加 512 维向量存储

---

## 当前局限（明确说清）

当前这版图搜图是：

- **结构正确**
- **链路跑通**
- **结果可用**
- 但还不是最终最强语义检索版本

原因是当前 embedding 仍基于：

- `phash` + `dhash`

它更偏：

- 近似图
- 同图 / 变体图
- 高度相似主图

而不是最强的“跨角度、跨背景、跨裁切”的语义视觉召回。

---

## 下一步建议

### P1：升级第二代 embedding

目标：

- provider 升级为 CLIP / OpenAI 视觉 embedding / 本地视觉模型
- 先新增 512 维向量存储或独立表
- 再启用第二套 provider/model 记录

### P2：前端接入拍照识别入口

目标：

- 报价页增加“上传图片找商品”入口
- 直接返回候选商品卡片

### P3：商城增量同步联动向量任务

目标：

- 新商品/新图片一旦同步进来
- 自动归档
- 自动生成 embedding

### P4：多阶段 rerank

目标：

- 图向量 Top-K 召回
- 再结合商品名 / 品牌 / 规格 / 历史反馈做 rerank

---

## 结论

这一轮之后，V2 已经不是“只规划图搜图”，而是已经具备：

- 图片归档层
- 图片 hash 层
- 向量层
- pgvector 检索层
- 以图搜图 API 层

后面要做的，就不是从零开始，而是**把当前可运行版本继续升级到更强语义视觉检索版本**。
