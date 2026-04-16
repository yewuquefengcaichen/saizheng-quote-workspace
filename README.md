# 赛正报价工作台

赛正报价工作台当前处于 **Flask 稳定工作台 + PostgreSQL V2 架构桥接** 阶段。

它已经可以完成：

- 商品库导入、浏览、筛选、详情查看
- 报价单上传、智能解析、候选匹配
- 人工确认、无匹配 / 问老板收口
- 图搜图辅助选品
- 图搜图 embedding provider 状态检查
- 批量调价、导出、历史记录、词库维护
- 手动把 legacy 商品库同步到 V2 PostgreSQL
- 查看 V2 同步新增 / 更新 / 无变化 / 旧图待处理统计
- 同步时自动重试异常行，并跳过未变化行的无意义写入
- 通过 Playwright 从商城页面抓取商品并同步到 V2
- 商城抓取支持预检模式，先看提取数量和预计差异，再决定是否写库
- 已接入赛正 dinghuovip 商品列表 DOM 专用适配器，可用登录态抓取真实商品列表
- 图搜图已接入 CLIP 512 维基础生成链路，并已生成首批真实 CLIP 向量

---

## 1. 当前定位

这个项目不是传统“满屏解释 + 满屏表格”的后台，而是围绕 **报价确认效率** 做的工作台：

- 左侧保留原始报价信息和必要动作
- 右侧专门处理候选商品选择
- 已确认项可折叠
- 商品详情走右侧抽屉
- 说明文字尽量退出业务页，统一收敛到 README / 说明页

---

## 2. 当前页面

- `/`：总览
- `/quotes`：报价工作台
- `/catalog`：商品库
- `/templates`：模板中心
- `/history`：历史记录
- `/synonyms`：同义词 / 词库
- `/guide`：说明页

---

## 3. 当前真实架构

### 工作台层

- Flask
- Jinja2
- 原生 JavaScript
- Bootstrap 5 + Bootstrap Icons

### V2 后端底座

- FastAPI
- SQLAlchemy 2.0 Async
- PostgreSQL
- Alembic
- pgvector

### 数据处理 / 图像能力

- pandas
- numpy
- openpyxl
- xlrd
- jieba
- Pillow
- Playwright

### 当前桥接状态

目前不是“全量新架构已完成”，而是 **双轨并行**：

- legacy 仍保留：
  - `data/products.json`
  - `data/quote_history.db`
  - `data/ai_cache.db`
  - `data/synonyms.json`
  - `data/parse_templates.json`
  - `data/normalization_rules.json`
- V2 已接入：
  - PostgreSQL 商品库
  - 图片归档与图搜图
  - 图搜图 provider 状态接口
  - `image_embeddings.embedding_vector` 128 维本地 hash 向量
  - `image_embeddings.embedding_vector_512` 512 维 CLIP / 更强模型向量
  - 商品手动同步任务
  - 商品库上传后可选“立即同步 V2”
  - 同步差异报告（新增 / 更新 / 无变化 / 旧图待处理）
  - 单行失败重试、失败样例记录、未变化行跳过写入
  - Playwright 商城抓取同步入口
  - 报价主匹配优先使用 PostgreSQL 商品快照
  - 报价项人工搜索优先查 PostgreSQL
  - 商品库列表页优先查 PostgreSQL
  - 商品详情优先查 PostgreSQL
  - 旧图片代理路由兼容 PostgreSQL 图片归档

---

## 4. 数据现在放在哪里

### 4.1 Legacy 目录：`data/`

#### SQLite

- `data/quote_history.db`
  - 报价历史
  - 已确认结果
  - 导出记录

- `data/ai_cache.db`
  - AI 缓存

#### JSON

- `data/products.json`
- `data/products.last_uploaded.json`
- `data/parse_templates.json`
- `data/synonyms.json`
- `data/normalization_rules.json`

### 4.2 V2 PostgreSQL

默认数据库：`saizheng_quote_v2`

当前核心表包括：

- `products`
- `product_variants`
- `product_images`
- `image_assets`
- `image_embeddings`：当前 128 维本地 hash 已可用，512 维 CLIP 也已可生成
- `brands`
- `categories`
- `suppliers`
- `synonyms`
- `normalization_rules`
- `parse_templates`
- `quote_batches`
- `quote_items`
- `match_feedback`
- `sync_jobs`
- `sync_job_logs`

### 4.3 图片归档

归档目录：

- `backend/storage/image_archive/product-images/`

说明：

- PostgreSQL 保存元数据、hash、向量和关联关系
- 实际图片文件保存在本地归档目录
- 前端通过 `/api/catalog/image_asset/<id>/file` 读取归档图片

> 结论：**现在项目已经同时使用 SQLite、JSON、PostgreSQL 和图片归档目录，不再只是单一 JSON。**

---

## 5. 当前已验证可用的重点能力

- 报价主匹配器：优先使用 PostgreSQL V2 商品快照
- 报价台人工文字搜商品：优先 PostgreSQL V2
- 图搜图：走 PostgreSQL + 图片归档 + 精排
- 图搜图状态：可查看当前 `local_hash_embedding` 是否就绪，以及 `clip_local` 依赖 / 维度是否满足
- 商品库列表页：优先 PostgreSQL V2
- 商品详情：优先 PostgreSQL V2
- 商品库页支持手动触发同步
- 上传商品库可选立即同步到 V2，并自动刷新运行时商品源
- V2 同步完成后会显示新增、更新、无变化、旧图待处理统计，并写入 `sync_jobs.stats_json`
- V2 同步已支持单行失败重试；未变化商品会跳过 product / variant / image 的无意义写入
- 商品库页新增“抓商城”按钮；后端会通过 Playwright 捕获页面网络 JSON，并用 DOM 商品卡片提取做兜底
- 商品库页新增“预检商城”按钮；不写库也能检查登录态、字段和预计同步差异
- 真实商城 `Product/ProductList` 已校准：`site_adapter=dinghuovip_product_list` 会解析 `#productList` 表格，避开通知 JSON 误判
- 商城列表页只提供封面图时，图片同步采用 `append_only`，不会把详情页历史图片误判成待删除旧图
- 商城分页已能跟随“下一页”链接继续抓取；详情补图开关已接入，可从商品详情页补齐主图和详情图
- 图搜图数据库已新增 512 维向量列；`clip_local` 当前显示为“结构支持、依赖可用”，并已生成首批 20 条真实 CLIP 向量
- 本项目 `backend\.venv` 已切到 RTX 4060 可用的 `torch 2.5.1+cu121`；这只影响项目虚拟环境，不改系统 CUDA 或其他深度学习环境
- 报价台以图识图已支持“快速图搜 / 智能 CLIP”切换
- CLIP 批量生成已有 Celery 任务入口，后续可接前端任务面板
- 首页 / 报价台 / 商品库会显示当前商品源状态
- Bootstrap Icons 改为本地静态资源，避免外网抖动导致图标问号 / 空框

当前已同步规模：

- 品牌：54
- 分类：104
- 供应商：9
- 商品：5886
- SKU / 变体：5886
- 商品图片：25755

最近一次真实商城预检结果：

- URL：`https://sz.dinghuovip.com/Product/ProductList`
- 登录态：本地 `backend/storage/mall-auth/saizheng-state.json`（已被 `.gitignore` 忽略，不提交）
- 适配器：`dinghuovip_product_list`
- 分页结果：访问 2 页，DOM 提取 20 行，去重后 15 个真实商品，未误抓通知 JSON
- 详情补图：测试抓取 1 个商品详情页，补到 4 张详情图
- 图搜图 CLIP：`clip_local / openclip_vit_b_32_512d` 已生成 20 条 512 维向量

---

## 6. 目录结构

```text
.
├─ app.py                               # Flask 主入口（5000）
├─ run_server.py                        # Waitress 入口（8080）
├─ README.md
├─ CHANGELOG.md
├─ data/                                # legacy SQLite + JSON
├─ output/                              # 导出与调试产物
├─ templates/                           # Jinja 模板
├─ static/                              # CSS / JS / 图片
├─ utils/                               # legacy 处理逻辑
└─ backend/                             # V2 FastAPI + PostgreSQL + pgvector
   ├─ app/
   ├─ alembic/
   ├─ scripts/
   └─ storage/image_archive/
```

---

## 7. 启动方式

### Flask 工作台（5000）

```powershell
cd "D:\A赛正\完整导出的商品信息\claudecode-报价系统"
backend\.venv\Scripts\python.exe app.py
```

访问：

```text
http://127.0.0.1:5000
```

### Waitress（8080）

```powershell
cd "D:\A赛正\完整导出的商品信息\claudecode-报价系统"
backend\.venv\Scripts\python.exe run_server.py
```

### V2 FastAPI（8001，可单独调试）

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

> 说明：为了让报价台也能用 RTX 4060 跑 CLIP，推荐用 `backend\.venv` 启动 Flask；这样不会污染系统 Python 或其他深度学习环境。

---

## 8. 回退到稳定版怎么做

当前建议保留两个明确锚点：

- 稳定分支：`stable/v0.9-quote-workbench`
- 稳定标签：`v0.9.0`

### 回到稳定标签

```powershell
git checkout v0.9.0
```

### 回到稳定分支

```powershell
git checkout stable/v0.9-quote-workbench
```

### 回到当前升级分支

```powershell
git checkout next/v2-architecture-upgrade
```

---

## 9. 后续升级方向

1. 继续把 legacy JSON 读路径往 PostgreSQL 收口
2. 继续增强商城全量抓取策略、详情补图限速、下架 / 删除策略和任务状态
3. 扩大 CLIP 向量生成范围，接入 provider 切换、历史反馈精排和结果缓存
4. 引入 Redis 做缓存、任务状态、热点检索优化
5. 继续拆分前后端，为 React / TypeScript 版本做准备

---

## 10. 关键文档

- `docs/UPGRADE_TASK_CHECKLIST.md`：V2 后续任务清单
- `docs/MALL_SCRAPE_SYNC.md`：商城抓取同步说明
- `docs/VERSION_POLICY.md`：版本命名、分支和标签规则
- `docs/BACKUP_RUNBOOK.md`：备份和回退操作

---

## 11. 一句话总结

当前这个版本已经不是纯 demo，而是一个 **能工作、可回退、并且正在向现代化 PostgreSQL / 向量检索架构升级** 的报价工作台。
