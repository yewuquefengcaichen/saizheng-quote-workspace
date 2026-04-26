# 赛正报价工作台

当前仓库是 **Flask 可用工作台 + PostgreSQL V2 升级桥接** 版本。

它已经能用于日常报价确认，不是纯演示版；同时它也还没有彻底去掉 legacy JSON / SQLite，因此现在是 **可工作、可回退、可继续升级** 的阶段。

当前阶段：**v0.9.1 上线前最后收口**。  
本轮已完成：**历史页 PostgreSQL 主读、词库 PostgreSQL 主读写、模板 PostgreSQL 主读写、图搜图 Redis 缓存第一版、历史反馈精排第一版、CLIP 全量向量生成**。  
CLIP 当前进度：`clip_local / openclip_vit_b_32_512d = 3300 / 3300`，`pending_assets = 0`。  
报价台当前默认保持：**连续下滑找候选**；以图识图当前默认保持：**智能 CLIP**，`近似图` 只作为辅助模式。  
下一次阶段停止点：完成“核心回归 + 文档齐套 + 版本冻结 + 上线准备”后先停一轮。  
阶段进度详见：`docs/PROJECT_PROGRESS.md`

---

## 1. 这个版本现在能做什么

- 导入商品库
- 上传 Excel 报价单 / OCR 图片报价
- 首页上传报价后，**直接进入 `/quotes` 报价台**
- 在报价台里做 **内嵌列映射确认**
- 左侧看原始报价，右侧选候选商品
- 人工确认 / 无匹配 / 问老板收口
- 商品详情右侧抽屉查看
- 图搜图辅助选品
- 批量调价
- 导出报价
- 查看历史记录、词库、模板中心
- 把 legacy 商品数据同步进 V2 PostgreSQL
- 通过 Playwright 抓商城商品并同步到 V2

---

## 2. 当前真实工作流

这是现在仓库里已经落地的主流程：

### 第 1 步：导入商品库

入口：

- 首页 `/`
- 商品库页 `/catalog`

作用：

- 先把商品底座导入工作台
- 导入后可选 **同步 V2**
- 后续报价匹配、人工搜索、图搜图都会更稳

### 第 2 步：上传报价

入口：

- 首页 `/`
- 报价台 `/quotes`

支持：

- Excel 报价单
- OCR 图片报价单

### 第 3 步：直接进入报价台

现在的行为已经不是“首页先卡一个大悬浮窗”。

当前实际流程是：

1. 在首页上传报价文件
2. 系统解析成功后，直接跳到 `/quotes`
3. 在报价台内显示 **列映射确认面板**
4. 确认列类型后，开始匹配

也就是说：

- **列映射确认还在**
- 但是它已经改成 **报价台内嵌确认**
- 不再先在首页弹一个很大的业务阻塞模态

### 第 4 步：在报价台确认候选

当前报价台是：

- 左边：原始报价信息、简要搜索、必要动作
- 中间 / 右边：候选商品、人工确认、详情抽屉

当前交互重点：

- 左右分栏可调
- 候选区有标准 / 紧凑视图
- 左列和候选列都支持更人性化的独立滚动
- 已确认项可折叠，减少干扰
- 商品详情走右侧抽屉，不再默认大模态

### 第 5 步：导出

确认完成后：

- 去模板中心选择导出形式
- 或直接从报价台进入导出

---

## 3. 当前页面

- `/`：总览 / 首页入口
- `/quotes`：报价台
- `/catalog`：商品库
- `/templates`：模板中心
- `/history`：历史记录
- `/synonyms`：词库
- `/guide`：说明页

---

## 4. 当前数据放在哪里

现在不是“所有数据都已经进数据库”，而是 **legacy + V2 双轨并行**。

### 4.1 Legacy：`data/`

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

这些文件说明：

- 老工作流还在用
- 部分页面 / 兼容链路还会读它们
- 其中 `data/synonyms.json` 现在已降级为**双写回退 / 备份位**，主读写已转到 PostgreSQL
- 其中 `data/parse_templates.json` 现在也已降级为**双写回退 / 备份位**，主读写已转到 PostgreSQL
- 所以现在还不能说“项目已经完全脱离 JSON”

### 4.2 V2：PostgreSQL

V2 目前已经接入 PostgreSQL，核心用途包括：

- 商品主数据
- 品牌 / 分类 / 供应商
- 商品图片元数据
- 图片向量
- 报价批次 / 报价项
- 匹配反馈
- 同步任务
- 历史页主读数据
- 词库主读写数据
- 模板主读写数据

当前常见核心表：

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

### 4.3 图片与图搜图

图片不是全部直接塞数据库二进制。

当前是：

- PostgreSQL：保存图片元数据、关联关系、向量信息
- 本地归档目录：保存实际图片文件

当前图片归档目录：

- `backend/storage/image_archive/product-images/`

前端读取路径：

- `/api/catalog/image_asset/<id>/file`

当前图搜图覆盖说明：

- 当前商品总数：**5892**
- 当前已进入图搜图向量覆盖的商品数：**2240**
- 当前 CLIP ready asset：**3300**

这意味着：

- **不是所有商品“存在于商品库”就一定已经具备图搜图能力**
- 只有已经归档图片并生成向量的商品，图搜图才能稳定命中
- 这也是“商品明明有，但图搜图偶尔识别不到”的真实原因之一

### 4.4 一句话总结

当前项目的数据层实际是：

- **JSON**
- **SQLite**
- **PostgreSQL**
- **本地图片归档**

并存。

这也是后续还要继续升级收口的重点。

---

## 5. 当前技术栈

### 5.1 工作台层

- Flask
- Jinja2
- 原生 JavaScript
- Bootstrap 5
- Bootstrap Icons

### 5.2 V2 后端层

- FastAPI
- SQLAlchemy 2.0 Async
- PostgreSQL
- Alembic
- pgvector

### 5.3 数据处理 / 同步 / 图像能力

- pandas
- numpy
- openpyxl
- xlrd
- jieba
- Pillow
- Playwright
- Celery
- Redis
- CLIP / 向量检索链路

### 5.4 现阶段架构特点

当前不是最终形态，而是：

- 前台工作台先保持可用
- V2 数据底座逐步接管
- 图搜图、商城同步、向量检索逐步迁入 V2

所以这个仓库更准确的定义是：

> **报价工作台可用版 + 新架构过渡版**

---

## 6. 启动方式

### Flask 工作台（推荐，5000）

```powershell
cd "D:\A赛正\完整导出的商品信息\claudecode-报价系统"
python run_server.py --port 5000
```

访问：

```text
http://127.0.0.1:5000
```

### Flask 工作台（8080）

```powershell
cd "D:\A赛正\完整导出的商品信息\claudecode-报价系统"
python run_server.py --port 8080
```

### V2 FastAPI（单独调试）

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

### PostgreSQL / Redis

```powershell
docker compose -f docker-compose.v2.yml up -d postgres redis
```

### Celery Worker

#### embedding 队列

```powershell
cd backend
.\.venv\Scripts\python.exe -m celery -A app.core.celery_app.celery_app worker -Q embedding --pool=solo --loglevel=info
```

#### sync 队列

```powershell
cd backend
.\.venv\Scripts\python.exe -m celery -A app.core.celery_app.celery_app worker -Q sync --pool=solo --loglevel=info
```

---

## 7. 当前版本怎么使用

如果你现在只想把这个版本当成“能用的报价系统”，最短路径就是：

1. 启动 Flask 工作台
2. 导入商品库
3. 首页上传报价单
4. 自动跳到 `/quotes`
5. 在报价台内确认列映射
6. 逐项确认候选商品
7. 导出

---

## 8. 如何回退到当前可用版本

当前仓库已经有明确锚点：

- 稳定分支：`stable/v0.9-quote-workbench`
- 稳定标签：`v0.9.0`
- 当前升级分支：`next/v2-architecture-upgrade`

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

如果你只是想“回到现在这个还能工作的版本”，最稳妥的做法是：

1. 给当前可用状态再打一个新 tag
2. 或者单独保留一个稳定分支
3. 后续升级都在 `next/...` 分支继续做

---

## 9. Tag / 分支 / 提交命名建议

### 9.1 当前建议

- 稳定分支继续保留：`stable/v0.9-quote-workbench`
- 升级分支继续开发：`next/v2-architecture-upgrade`
- 当前这次可用状态建议再打一个标签，例如：
  - `v0.9.1`
  - 或 `v0.9.1-quote-workbench-refine`

### 9.2 提交信息建议

以后尽量写成“中文为主 + 英文类型前缀”：

例如：

- `feat(报价台): 首页上传后直接进入报价台内嵌映射确认`
- `fix(商品库): 修正左栏独立滚动和图片优先显示`
- `docs(README): 补充数据存储与回退说明`

这样以后你在 GitHub 上一眼就能看懂，不会只看到一串 hash。

---

## 10. 当前版本为什么值得单独留档

因为它已经具备这些条件：

- 不是纯静态页面
- 有真实报价工作流
- 有商品库、报价台、模板、历史、词库
- 有 V2 PostgreSQL 接入
- 有图搜图和商城同步方向
- 已经形成可回退版本锚点

所以这个版本**有资格保留独立分支 / 标签**。

---

## 11. 后续升级方向

后续不是“推倒重来”，而是继续把现在这套系统升级成更现代的版本。

核心方向：

1. 继续把 legacy JSON / SQLite 读写收口到 PostgreSQL
2. 继续增强商城同步、失败页重跑、断点续抓、疑似下架判断
3. 扩大图片向量覆盖率，让图搜图真正可用于大规模商品库
4. 加 Redis 做缓存、任务状态和热点数据提速
5. 继续拆分前后端，为后续 React / TypeScript 重构铺路

---

## 12. 关键文档

- `docs/UPGRADE_TASK_CHECKLIST.md`
- `docs/PROJECT_UPGRADE_TASKS.md`
- `docs/ARCHITECTURE_V2_PLAN.md`
- `docs/MALL_SCRAPE_SYNC.md`
- `docs/VERSION_POLICY.md`
- `docs/BACKUP_RUNBOOK.md`

---

## 13. 一句话总结

当前版本可以理解成：

> **一个已经能工作的报价确认工作台，底层正在从 legacy JSON / SQLite 逐步升级到 PostgreSQL + 向量检索架构。**
