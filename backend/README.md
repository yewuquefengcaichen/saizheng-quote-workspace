# V2 后端说明

`backend/` 是赛正报价工作台的 V2 后端底座，目标是把 legacy 的 JSON / SQLite 工作流逐步迁到更稳的现代架构上。

当前阶段：**v0.9.1 上线前最后收口**。

当前已经承接：

- PostgreSQL 商品库
- 图片归档与去重
- 图搜图与精排
- 商品同步任务
- Playwright 商城抓取同步第一版
- 赛正 dinghuovip 商品列表 DOM 适配器
- CLIP 512 维图片向量生成链路
- 规则 / 历史 / 反馈迁移底座
- 未来 React 前端 API

---

## 1. 技术栈

- FastAPI
- SQLAlchemy 2.0 Async
- PostgreSQL
- Alembic
- pgvector
- pgvector 128/512 双向量列
- Pillow
- Playwright
- Redis / Celery（预留升级位）

---

## 2. 当前数据规模

- brands: 54
- categories: 104
- suppliers: 9
- products: 5886
- variants: 5886
- product_images: 25755
- synonyms: 84
- normalization_rules: 25
- parse_templates: 5
- quote_batches: 1
- quote_items: 19
- match_feedback: 83

---

## 3. 运行方式

```powershell
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

健康检查：

```text
http://127.0.0.1:8001/health
```

---

## 4. 主要 API

### 图片检索

- `POST /api/v1/image-search/query`
- `GET /api/v1/image-search/assets/{asset_id}/file`
- `GET /api/v1/image-search/embedding-status`

当前状态：

- `local_hash_embedding / phash_dhash_128d_v1`：生产可用，写入 `embedding_vector vector(128)`
- `clip_local / openclip_vit_b_32_512d`：依赖已接入，写入 `embedding_vector_512 vector(512)`；当前已完成全量生成 `3300 / 3300`，`pending_assets = 0`

### 商品同步

- `GET /api/v1/catalog-sync/latest`
- `POST /api/v1/catalog-sync/manual`

---

## 5. 关键脚本

### 导入 legacy 商品

```powershell
backend\.venv\Scripts\python.exe backend\scripts\import_legacy_products.py
```

### 导入 legacy 规则

```powershell
backend\.venv\Scripts\python.exe backend\scripts\import_legacy_rules.py
```

### 导入 legacy 历史 / 反馈

```powershell
backend\.venv\Scripts\python.exe backend\scripts\import_legacy_history.py
```

### 图片归档

```powershell
backend\.venv\Scripts\python.exe backend\scripts\archive_product_images.py --only-missing-asset
```

### 生成图片向量

```powershell
backend\.venv\Scripts\python.exe backend\scripts\generate_image_embeddings.py
```

检查 CLIP 状态：

```powershell
backend\.venv\Scripts\python.exe backend\scripts\generate_image_embeddings.py --provider clip_local --model-name openclip_vit_b_32_512d --dry-run --limit 1
```

增量生成 CLIP 向量：

```powershell
backend\.venv\Scripts\python.exe backend\scripts\generate_image_embeddings.py --provider clip_local --model-name openclip_vit_b_32_512d --limit 20 --commit-every 5
```

全量 / 增量 CLIP 分批慢跑（推荐）：

```powershell
backend\.venv\Scripts\python.exe backend\scripts\generate_image_embeddings_batch.py --provider clip_local --model-name openclip_vit_b_32_512d --batch-size 20 --commit-every 5 --sleep-seconds 1.5
```

按批次数限制（例如先跑 50 批）：

```powershell
backend\.venv\Scripts\python.exe backend\scripts\generate_image_embeddings_batch.py --provider clip_local --model-name openclip_vit_b_32_512d --batch-size 20 --max-batches 50
```

说明：

- 当前 Windows 环境使用 RTX 4060 验证通过的 CUDA 版：`torch==2.5.1+cu121`
- 这个 CUDA 来自 PyTorch wheel，只安装在 `backend\.venv`，不会改系统 CUDA Toolkit 或其他 Conda 环境
- 首次运行会从 Hugging Face / OpenCLIP 下载模型权重
- 当前本地 CLIP 首轮全量已完成：`3300 / 3300`，`pending_assets = 0`
- 若商城有新品、补图或失败资产，建议继续分批执行增量补跑，不阻塞前台页面
- `--limit 10~20` 现在主要用于增量补跑、依赖验证或回归，不再代表全量完成度

---

## 6. 当前桥接状态

当前 Flask 工作台已经直接在用 V2 的这些能力：

- 商品库列表页优先查 PostgreSQL
- 商品详情优先查 PostgreSQL
- 报价项人工搜索优先查 PostgreSQL
- 图搜图直接查 PostgreSQL / 图片归档 / 精排结果
- 商品库页支持手动触发同步
- 商品库页支持手动触发 Playwright 商城抓取后台同步
- 商城抓取支持 `site_adapter=dinghuovip_product_list`，可解析真实 `#productList` 表格
- 商城抓取支持“下一页”分页、可选详情页补图、页间限速和断点续抓
- 报价台以图识图支持“快速图搜 / 智能 CLIP”模式切换
- CLIP 批量生成已具备 Celery 任务入口，并已桥接到 Flask 商品库页任务面板

---

## 7. Celery 后台任务

先启动 Redis：

```powershell
cd ..
docker compose -f docker-compose.v2.yml up -d redis
cd backend
```

当前已提供后台任务：

```text
app.tasks.embedding.generate_image_embeddings
app.tasks.catalog.scrape_mall_sync
```

启动 worker 示例：

```powershell
cd backend
.\.venv\Scripts\python.exe -m celery -A app.core.celery_app.celery_app worker -Q embedding --pool=solo --loglevel=info
```

商城抓取 / 同步 worker：

```powershell
.\.venv\Scripts\python.exe -m celery -A app.core.celery_app.celery_app worker -Q sync --pool=solo --loglevel=info
```

提交任务 API：

```text
POST /api/v1/image-search/embedding-jobs
GET  /api/v1/image-search/embedding-jobs/{task_id}
```

Flask 工作台桥接 API：

```text
POST /api/catalog/image_embedding_jobs
GET  /api/catalog/image_embedding_jobs/{task_id}
POST /api/catalog/mall_sync_jobs
GET  /api/catalog/mall_sync_jobs/{task_id}
```

前端入口：

```text
/catalog -> 生成 CLIP
/catalog -> 小批量 / 全量抓商城
```

商城抓取可用参数：

```json
{
  "max_pages": 100,
  "start_page": 1,
  "max_items": 0,
  "page_delay_ms": 1200,
  "next_delay_ms": 900,
  "detail_delay_ms": 800,
  "checkpoint_path": "backend/storage/mall-sync-checkpoints/catalog-mall-latest.json",
  "resume_from_checkpoint": true
}
```

断点文件在 `backend/storage/` 下，已被 `.gitignore` 忽略，不会提交。

示例请求体：

```json
{
  "provider": "clip_local",
  "model_name": "openclip_vit_b_32_512d",
  "limit": 20,
  "commit_every": 5,
  "only_missing": true,
  "dry_run": false
}
```

## 8. 数据库存储说明

- PostgreSQL 保存：商品、分类、品牌、供应商、图片元数据、向量、规则、历史、反馈、同步任务
- 本地文件系统保存：图片归档文件
- legacy `data/` 目录暂时保留，用于兼容和回退

---

## 9. 维护提醒

如果手动同步前后遇到 PostgreSQL 索引异常，可参考 `docs/BACKUP_RUNBOOK.md`：

- `REINDEX INDEX ix_products_normalized_name`
- `REINDEX INDEX uq_products_source_external_product`
- `REINDEX TABLE products`
