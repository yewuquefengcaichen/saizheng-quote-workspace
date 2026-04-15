# 图片归档进度报告（2026-04-15）

## 本轮结论

V2 已经从“只有图片 URL”推进到“**图片资产可落库、可归档、可去重、可算 hash、可为图搜图做前置准备**”。

本轮已经完成：

1. 追出旧系统图片真实访问逻辑
2. 新增 `image_assets` / `image_embeddings` 数据表
3. 给 `product_images` 增加资产关联与归档状态字段
4. 落地本地图片归档与 hash 计算脚本
5. 实际写入 PostgreSQL + 本地归档目录，完成全量真实数据验证

---

## 关键发现

旧系统 `products.json` / `product_images.source_url` 里的图片地址几乎全部是相对路径，例如：

```text
../Upload/7114ea97-d7fb-45af-9aee-e3642678ea41/.../ProductDescription/...jpg
```

旧系统真实图片访问链路已经确认：

- 商城页面基址：`https://sz.dinghuovip.com`
- 文件实际域名：`https://udeanfile.dinghuovip.com`

也就是说：

- 页面搜索、商品详情等 HTML 仍来自 `sz.dinghuovip.com`
- 图片文件本体应切到 `udeanfile.dinghuovip.com`

这条规则已经沉淀进：

- `backend/app/services/image_pipeline.py`

---

## 已落地的数据库结构

### 新表

- `image_assets`
  - 存唯一图片资产
  - 关键字段：`sha256`、`storage_key`、`mime_type`、`width`、`height`、`file_size`、`phash`、`dhash`

- `image_embeddings`
  - 存图向量任务位与向量结果占位
  - 当前先落 schema，为后续 `pgvector` / CLIP embedding 做准备

### 追加到 `product_images` 的字段

- `asset_id`
- `resolved_url`
- `download_attempts`
- `last_downloaded_at`
- `sync_message`

Alembic 版本已推进到：

- `20260415_0004`

---

## 已新增的脚本与服务

### 服务层

- `backend/app/services/image_pipeline.py`

职责：

- 相对 URL => 真实图片 URL
- 下载图片
- 计算 `sha256`
- 计算 `phash` / `dhash`
- 获取图片尺寸 / MIME
- 归档到本地文件系统

### CLI 脚本

- `backend/scripts/archive_product_images.py`

用途：

- 批量处理 `product_images`
- 下载图片并归档到 `backend/storage/image_archive/`
- 去重写入 `image_assets`
- 回写 `product_images.asset_id` / `sha256` / `phash` / `dhash` / `storage_key`
- 优先复用已归档图片，避免重复下载同一个 `source_url`

示例命令：

```bash
python backend/scripts/archive_product_images.py --limit 100 --commit-every 25 --only-missing-asset
```

---

## 已完成的真实验证结果

### 1）Dry-run 验证

执行：

```bash
python backend/scripts/archive_product_images.py --limit 5 --dry-run --commit-every 5
```

结果：

- 5/5 成功
- 0 失败
- 证明下载、解析、hash、入库逻辑都能跑通

### 2）真实写入验证

已真实执行：

```bash
python backend/scripts/archive_product_images.py --limit 100 --commit-every 25 --only-missing-asset
python backend/scripts/archive_product_images.py --limit 1000 --commit-every 100 --only-missing-asset
python backend/scripts/archive_product_images.py --limit 2000 --commit-every 200 --only-missing-asset
python backend/scripts/archive_product_images.py --commit-every 500 --only-missing-asset
```

当前 PostgreSQL 实际状态：

- `product_images` 总数：`25755`
- 已归档 `sync_status = 'archived'`：`25755`
- 仍待归档 `sync_status = 'pending'`：`0`
- 失败数 `sync_status = 'failed'`：`0`
- `image_assets` 唯一图片资产：`3300`
- 已关联 `asset_id` 的 `product_images`：`25755`
- 已生成去重后本地归档文件：`3300`
- 当前本地归档文件体积：`706,631,034 bytes`（约 673.90 MB）
- `sha256` / `phash` / `dhash` 完整覆盖：`25755 / 25755 / 25755`

### 3）数据结论

全量 25755 条图片记录最终沉淀出 3300 个唯一资产，说明：

- 旧商城确实存在大量“同图复用到多个 SKU/多个报价项”的情况
- “`product_images` 只存引用，`image_assets` 存唯一资产”的建模方向是对的
- 后续做图搜图、OCR、embedding 时，**应该对 `image_assets` 做特征提取，而不是对每条 `product_images` 重复算一遍**
- 归档脚本加入“按 `source_url` 复用已归档资产”的缓存策略后，全量归档速度明显提升，后续增量同步也能直接受益

这会直接减少后续计算量与存储量。

---

## 本轮涉及文件

### 代码

- `backend/app/core/config.py`
- `backend/app/models/catalog.py`
- `backend/app/models/__init__.py`
- `backend/app/services/__init__.py`
- `backend/app/services/image_pipeline.py`
- `backend/scripts/archive_product_images.py`
- `backend/alembic/versions/20260415_0004_init_image_asset_tables.py`
- `backend/.env.example`
- `backend/requirements.txt`
- `.gitignore`

### 数据目录

- `backend/storage/image_archive/`（已加入 `.gitignore`）

---

## 这一步对后续图搜图的价值

现在已经具备：

- 稳定的图片下载规则
- 唯一资产层
- hash 层（`sha256` / `phash` / `dhash`）
- 归档层
- 向量表预留层

所以后续图搜图可以按正确路线继续：

1. 对 `image_assets` 跑 embedding（而不是对每条 `product_images`）
2. 引入 `pgvector`
3. 增加“拍照上传 -> embedding -> Top-K 相似商品召回 -> 再结合名称/品牌/规格 rerank”链路
4. 给商城增量同步链路挂上“新图自动归档 / 自动入向量队列”

---

## 下一步建议（已排好优先级）

### P1：补 `image_embeddings` 生产链路

目标：

- 对 `image_assets` 生成向量
- 先落任务链路与状态流转
- 再切 `pgvector`

### P2：增加“手动同步商城图片/商品”的后台任务

目标：

- 手动点击一次，重新从商城抓增量商品
- 同步新增商品与图片
- 把新图片自动送入归档队列

### P3：图片检索 API + 识图入口

目标：

- 上传图片
- 生成 embedding
- 查相似商品
- 回传候选商品列表给报价页面

---

## 备注

当前阶段优先把“图片资产底座”做实，暂时先用本地文件系统归档；
后续接 MinIO / S3 时，不需要改业务模型，只需要替换 `storage_backend + storage_bucket + storage_key` 的落地实现。
