# 赛正报价工作台

赛正报价工作台当前处于 **Flask 稳定工作台 + PostgreSQL V2 架构桥接** 阶段。

它已经可以完成：

- 商品库导入、浏览、筛选、详情查看
- 报价单上传、智能解析、候选匹配
- 人工确认、无匹配 / 问老板收口
- 图搜图辅助选品
- 批量调价、导出、历史记录、词库维护
- 手动把 legacy 商品库同步到 V2 PostgreSQL
- 查看 V2 同步新增 / 更新 / 无变化 / 旧图待处理统计
- 同步时自动重试异常行，并跳过未变化行的无意义写入
- 通过 Playwright 从商城页面抓取商品并同步到 V2

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
- `image_embeddings`
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
- 商品库列表页：优先 PostgreSQL V2
- 商品详情：优先 PostgreSQL V2
- 商品库页支持手动触发同步
- 上传商品库可选立即同步到 V2，并自动刷新运行时商品源
- V2 同步完成后会显示新增、更新、无变化、旧图待处理统计，并写入 `sync_jobs.stats_json`
- V2 同步已支持单行失败重试；未变化商品会跳过 product / variant / image 的无意义写入
- 商品库页新增“抓商城”按钮；后端会通过 Playwright 捕获页面网络 JSON，并用 DOM 商品卡片提取做兜底
- 首页 / 报价台 / 商品库会显示当前商品源状态
- Bootstrap Icons 改为本地静态资源，避免外网抖动导致图标问号 / 空框

当前已同步规模：

- 品牌：54
- 分类：104
- 供应商：9
- 商品：5886
- SKU / 变体：5886
- 商品图片：25755

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
python app.py
```

访问：

```text
http://127.0.0.1:5000
```

### Waitress（8080）

```powershell
cd "D:\A赛正\完整导出的商品信息\claudecode-报价系统"
python run_server.py
```

### V2 FastAPI（8001，可单独调试）

```powershell
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

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
2. 继续校准商城抓取登录态、起始 URL、分页和选择器
3. 为“以图识图”继续增强图像特征与召回链路
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
