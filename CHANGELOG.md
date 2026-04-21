# 更新日志

> 项目：赛正报价工作台  
> 说明：稳定版继续可回退可使用，V2 架构升级在 `next/v2-architecture-upgrade` 分支持续推进。

---

## v0.9.0 - 稳定版冻结（2026-04-15）

### 基线信息

- 稳定分支：`stable/v0.9-quote-workbench`
- 标签：`v0.9.0`
- 基线提交：`ffffe34`
- 定位：当前可回退、可继续使用的工作台版本

### 稳定版能力

- Flask + Jinja2 报价工作台
- 商品库导入、报价单上传、候选匹配
- 人工确认、无匹配、问老板收口
- 调价、导出、历史记录、模板中心
- 报价页左右分栏与高密度确认流

### 稳定版数据

- 商品库：`data/products.json`
- 历史报价：`data/quote_history.db`
- AI 缓存：`data/ai_cache.db`
- 规则模板：`data/synonyms.json`、`data/parse_templates.json`、`data/normalization_rules.json`

---

## 2026-04-16 - 当前 V2 升级进度

### 已完成

- PostgreSQL + SQLAlchemy 2.0 + Alembic 底座
- 商品、规则、历史反馈迁入 PostgreSQL
- 图片归档、去重资产层与 `pgvector`
- 第一版图搜图 API 落地
- Flask 报价台桥接图搜图闭环
- 报价项支持“上传图片 -> 返回候选 -> 点选回填”
- 新增手动同步入口，可把当前 `products.json` 同步进 V2
- 报价主匹配器改为优先使用 PostgreSQL V2 商品快照
- 商品库列表页改为优先查 PostgreSQL V2
- 商品详情改为优先查 PostgreSQL V2
- 上传商品库新增“立即同步 V2”可选链路
- 首页 / 报价台 / 商品库增加当前商品源状态标识
- 旧图片代理路由兼容 PostgreSQL 归档图
- Bootstrap Icons 改为本地静态资源，降低图标乱码 / 问号风险
- 核心 README / Runbook / 版本文档已清理乱码并重写
- V2 商品同步增加差异报告：新增 / 更新 / 无变化 / 旧图待处理，并在前端同步状态中展示
- V2 商品同步增加单行失败重试和失败样例统计
- V2 商品同步增加第一版增量写入策略：无变化行跳过 product / variant / image 无意义写入
- 新增 Playwright 商城抓取同步第一版：支持网络 JSON 捕获、DOM 商品卡片兜底、商品库页“抓商城”按钮
- 新增商城抓取预检：不写库即可检查页面、候选数量、登录态风险、字段样例和预计差异
- 图搜图新增 embedding provider 状态接口，并让生成脚本支持 `--provider / --model-name` 参数，为 CLIP 升级打底
- 商城抓取完成真实赛正 dinghuovip 商品列表适配：`site_adapter=dinghuovip_product_list` 可解析 `#productList` 表格
- 商城抓取新增网络 include / exclude 过滤，避免通知公告 JSON 被误判成商品
- 商品同步开始直接兼容 `image_urls / primary_image_url`，列表页封面图采用 `append_only` 模式避免误伤历史详情图
- 图搜图新增 `embedding_vector_512` 数据库列和 HNSW 索引，随后补齐依赖并接入 CLIP 生成器
- 修复 `run_server.py` 导入方式：避免根目录 `app.py` 与 `backend/app` 包同名导致 V2 模块被禁用
- 补齐 `backend\.venv` 关键依赖：`pgvector / ImageHash / Playwright / torch CUDA / open_clip_torch`，并安装 Chromium
- 已验证 RTX 4060 Laptop GPU：`torch 2.5.1+cu121`、`cuda_available=True`、GPU 矩阵运算通过；其他 Python 环境未被修改
- 商城抓取新增真实分页跟随能力，可从 `下一页` 链接继续抓取
- 商城抓取新增可选详情页补图：`fetch_detail_images / detail_fetch_limit / detail_image_limit_per_item`
- 图搜图 CLIP 生成器基础链路落地：可生成 `clip_local / openclip_vit_b_32_512d` 的 512 维向量
- 已实际生成首批 20 条 CLIP 512 维向量，并验证 CLIP 查询可返回结果
- 报价台以图识图新增“快速图搜 / 智能 CLIP”切换，前端会把 provider / model 传给后端
- 新增 Celery embedding 任务入口：`app.tasks.embedding.generate_image_embeddings`
- 新增 FastAPI embedding job API：`POST /api/v1/image-search/embedding-jobs` 与任务状态查询
- 新增 Flask 商品库 embedding job 桥接 API：`POST /api/catalog/image_embedding_jobs` 与状态查询
- 商品库页新增“生成 CLIP”入口，可查看快速 / CLIP 向量 ready 与 pending，并提交每批 20 张的后台生成任务
- 新增商城抓取后台任务：`app.tasks.catalog.scrape_mall_sync`
- 商品库页“抓商城”改为提交后台任务，前端轮询 `/api/catalog/mall_sync_jobs/{task_id}`，完成后刷新商品源和向量状态
- 商城抓取新增小批量 / 全量参数入口，并支持 `start_page / max_items / page_delay_ms / next_delay_ms / detail_delay_ms`
- 商城抓取新增断点文件：支持 `checkpoint_path / resume_from_checkpoint`，中断后可从下一页或模板页码继续
- 修复商品库默认排序：打开商品库优先展示有图商品，并刷新图片脚本缓存，避免满屏空图误判为图片链路失效
- 修复首页上传报价后切到报价台时仍按首页路由渲染的问题，报价确认区会使用报价台的紧凑布局
- 推荐使用 `backend\.venv\Scripts\python.exe app.py` 启动 Flask，以便报价台直接使用 RTX 4060 的 CLIP 能力

### 当前重点

1. 真实跑小批量商城抓取与 CLIP worker，确认任务队列稳定
2. 增强商城下架 / 删除策略、断点批次记录和失败项重跑
3. 图搜图历史反馈精排、拍照 / 粘贴图片入口增强
4. 继续把 legacy JSON 读路径往 PostgreSQL 收口
5. 为后续 React / TypeScript 重构打基础
