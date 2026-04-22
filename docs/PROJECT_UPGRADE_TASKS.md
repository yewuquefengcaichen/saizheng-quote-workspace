# 项目升级落地任务清单

> 这份文档给后续继续开发用：先保证当前报价工作台能用，再逐步把数据、图片、商城同步、图搜图和后台任务迁到更现代的架构。

## 0. 当前状态结论

- 当前版本属于 **Flask 稳定工作台 + PostgreSQL V2 桥接版**。
- 商品库已经优先读取 PostgreSQL，并且已验证首页商品图接口正常。
- 报价台已改成左侧原始报价信息、右侧候选商品选择；支持标准 / 紧凑视图、左右栏拖动、商品详情右侧抽屉。
- 商城没有官方 API，所以现阶段采用 **登录态 + Playwright 抓商城页面 + DOM/网络数据解析 + 手动触发同步**。
- 图搜图已进入第二阶段：本地 hash 向量已可用，CLIP 512 维向量已接入，后续要批量生成全量向量并做反馈精排。

## 1. 今天必须重点盯住的 P0

| 优先级 | 模块 | 任务 | 状态 | 说明 |
|---|---|---|---|---|
| P0 | 商品库图片 | 商品库第一页优先展示有图商品 | 已完成 | 后端按有图优先排序，图片接口返回 `200 image/jpeg` |
| P0 | 商品库图片 | 前端图片兜底 | 已完成 | 优先使用 `/api/catalog/image_asset/<id>/file` |
| P0 | 报价台 | 首页上传报价后进入紧凑报价台 | 已完成 | `data-route` 已同步为 `quotes`，不会再按首页大块样式渲染 |
| P0 | 报价台 | 候选区滚动和阅读效率 | 本轮精修 | 候选区独立滚动，标准视图图片放大，左栏默认更窄 |
| P0 | 缓存 | 防止浏览器继续拿旧 JS/CSS | 本轮精修 | 静态资源版本号已提升 |
| P0 | Windows 编码 | 全局记录 PowerShell 乱码根因 | 已完成 | 写入 `C:\Users\30431\.codex\AGENTS.md` |

## 2. 数据到底放在哪里

### 2.1 PostgreSQL：后续主数据库

主要承载：

- 商品主档、SKU、分类、品牌、供应商
- 图片资产 `image_assets`
- 图搜图向量 `image_embeddings`
- 同步任务 `sync_jobs / sync_job_logs`
- 后续计划承载模板、词库、历史报价

### 2.2 SQLite：当前 legacy 运行数据

仍然存在：

- `data/quote_history.db`：报价历史、确认结果、导出记录
- `data/ai_cache.db`：旧 AI 缓存

### 2.3 JSON：后续会逐步降级为导入/备份中间态

当前仍然存在：

- `data/products.json`
- `data/synonyms.json`
- `data/parse_templates.json`
- `data/normalization_rules.json`

原则：

- 不能一下子全部砍掉，因为老 Flask 工作台还在读部分 JSON。
- 后续每迁一个模块，都要做到“PostgreSQL 可读写 + JSON 可备份/回滚”。
- `data/synonyms.json`、`data/parse_templates.json` 是本地运行态文件，默认不要误提交。

## 3. 商城同步方案

因为商城没有官方 API，推荐路线是：

1. 本地保存后台登录态到 `backend/storage/mall-auth/`，不进 Git。
2. 用户在商品库页点击“预检商城”，先 dry-run 看能抓到多少商品。
3. 再点击“小批量 / 全量抓商城”，后台 Celery `sync` 队列执行。
4. 抓取时写 checkpoint，支持断点续抓。
5. 抓完后写 PostgreSQL，不直接覆盖删除老商品。

必须补的下架策略：

- 新批次没看到的商品先标记为 `missing_in_latest_scrape`。
- 连续多次没看到再标记 `inactive`。
- 不直接物理删除，避免商城登录异常或页面变动造成误删。
- 前端商品库要能筛选：在售 / 疑似下架 / 已下架 / 待复核。

## 4. 图搜图 / 拍照识别方案

当前能力：

- 本地图片 hash 向量：快，适合粗召回。
- CLIP 512 维向量：更适合拍照、相似商品、不同角度图片。
- RTX 4060 笔记本 GPU 已验证可用，当前 PyTorch 为 `2.5.1+cu121`。

后续任务：

| 优先级 | 任务 | 说明 |
|---|---|---|
| P1 | 全量生成 CLIP 向量 | 几万张图片要分批跑，不能一次塞爆显存 |
| P1 | 拍照 / 粘贴图片入口 | 报价台和商品库都需要 |
| P1 | 图搜图结果缓存 | Redis 可缓存热门图片 hash / CLIP 查询 |
| P2 | 历史确认反馈精排 | 用户点过、确认过的结果应排更靠前 |
| P2 | 多图联合判断 | 一个 SKU 多张图时合并评分 |

注意：

- 不是“必须重新训练模型”才能识别；第一阶段使用预训练 CLIP 生成向量即可。
- 真正的训练 / 微调属于后续高级阶段，等有足够确认样本后再做。

## 5. Redis / Celery 应该怎么用

Redis 不负责永久保存商品数据，它适合：

- Celery 任务队列 broker / result backend
- 同步任务状态缓存
- 热门搜索缓存
- 图搜图查询缓存
- 前端轮询状态临时缓存

Celery 适合：

- 商城抓取
- 全量图片归档
- 全量 CLIP 向量生成
- 大批量导入 / 差异同步
- 长耗时 OCR / 图片识别任务

## 6. 后续执行顺序

### P1：先让 V2 真正稳定

1. 商城同步批次表：每次抓取有 batch id。
2. 每页抓取日志：页码、URL、提取数、失败原因。
3. 失败页重跑。
4. 下架 / 疑似删除策略。
5. 前端显示最近同步批次和异常项。

### P2：让图搜图进入可用生产状态

1. 全量 CLIP 512 维向量生成。
2. 拍照 / 粘贴图片识别入口。
3. 结果缓存。
4. 历史确认反馈 rerank。

### P3：收口数据库

1. 历史页读写 PostgreSQL。
2. 同义词读写 PostgreSQL。
3. 模板规则读写 PostgreSQL。
4. JSON 退为导入/导出备份，不再做主数据源。

### P4：新架构重构方向

1. 后端 API 契约稳定：FastAPI + Pydantic schema。
2. 前端新工程：React + TypeScript。
3. UI 组件化：报价项、候选商品、商品详情、同步任务面板独立组件。
4. 性能基线：首屏、商品检索、图搜图、导出耗时都要有数据。
5. 备份恢复：PostgreSQL、图片资产、商城同步状态都要能恢复。

## 7. 当前版本回退和版本识别

- 稳定标签：`v0.9.0`
- 稳定分支：`stable/v0.9-quote-workbench`
- 当前升级分支：`next/v2-architecture-upgrade`

常用命令：

```powershell
git status --short --branch
git tag --list
git checkout v0.9.0
git checkout next/v2-architecture-upgrade
```

后续每次重要改动都要：

1. 中文 commit 说明。
2. README 或 docs 记录改了什么。
3. 能跑的验证命令。
4. 推送到 GitHub。

