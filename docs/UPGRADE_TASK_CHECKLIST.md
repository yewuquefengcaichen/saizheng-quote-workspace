# V2 升级任务清单

> 这份清单只记录现在真实有效的升级工作，不再保留乱码内容。

> 状态说明：`[x]` 已完成、`[ ]` 待做。

> 当前阶段：`v0.9.1 上线前最后收口`。

---

## A. 总目标

- 稳住当前 Flask 工作台的可用性
- 把商品、规则、历史、图片能力迁到 PostgreSQL
- 建立可持续扩展的同步链路、图搜图链路和未来新前端底座

---

## B. 稳定版冻结

- [x] 建立稳定分支 `stable/v0.9-quote-workbench`
- [x] 打 `v0.9.0` 标签
- [x] 写清楚版本治理与回退方式
- [ ] 补 GitHub Release 页面说明

---

## C. V2 基础设施

- [x] 初始化 `backend/` FastAPI 项目
- [x] 接入 PostgreSQL + SQLAlchemy 2.0
- [x] 接入 Alembic
- [x] 接入 Redis / Celery 基础骨架
- [x] 补 `.env.example`
- [x] 补 `/health` 健康检查

---

## D. 数据迁移

### 商品数据

- [x] 迁移 `data/products.json` 到 `products / product_variants / product_images`
- [x] 建立品牌、分类、供应商表
- [x] 生成首批导入报告
- [ ] 让更多商品读路径直接走 PostgreSQL

### 规则与历史

- [x] 迁移同义词、模板规则
- [x] 迁移历史报价与反馈
- [x] 补迁移报告

---

## E. 图片资产与图搜图

- [x] 建立 `image_assets` / `image_embeddings`
- [x] 全量归档商品图片
- [x] 补齐 `asset_id / sha256 / phash / dhash`
- [x] 接入 `pgvector`
- [x] 生成第一版 `local_hash_embedding`
- [x] 新增 `POST /api/v1/image-search/query`
- [x] 新增 `GET /api/v1/image-search/assets/{asset_id}/file`
- [x] Flask 报价台桥接图搜图
- [x] 报价台完成上传图片选 SKU 闭环
- [x] 加入第一轮文本 / 规格精排
- [x] 增加 embedding provider 状态接口
- [x] 预留第二代视觉 embedding 的 512 维向量列与索引
- [x] 接入真正的 CLIP / 更强 provider 生成器基础链路
- [x] 生成首批 CLIP 512 维向量
- [x] 批量生成全量 CLIP 512 维向量（`3300 / 3300`，`pending_assets = 0`）
- [x] 商品库页接入 CLIP 向量后台任务面板
- [x] 接入历史反馈精排

---

## F. 商品同步

- [x] 保留“上传商品库 -> 刷新 `products.json`”旧链路
- [x] 新增手动“同步 V2”入口
- [x] 上传商品库后可选“立即同步 V2”
- [x] 同步结果写入 `sync_jobs / sync_job_logs`
- [x] 增加差异同步统计
- [x] 增加失败重试
- [x] 增加增量同步策略（第一版：无变化行跳过写入）
- [x] 增加 Playwright 商城抓取同步源（第一版）
- [x] 完成赛正 dinghuovip 商品列表真实 DOM 适配
- [x] 商城抓取支持网络 include / exclude 过滤，避免通知 JSON 误判
- [x] 商城抓取分页增强
- [x] 商品详情页补图基础能力
- [x] 商城抓取同步后台任务入口
- [x] 全量抓取限速 / 断点续抓基础能力

---

## G. 当前工作台桥接

- [x] 报价主匹配优先读取 PostgreSQL 商品快照
- [x] 报价项文字搜可用于人工选品
- [x] 报价项以图识图可回填当前项
- [x] 首页上传报价后直接跳到 `/quotes`
- [x] 列映射确认改为报价台内嵌确认面板
- [x] 报价台左列补独立滚动
- [x] 报价台候选图片区首屏优先加载
- [x] 首页 / 商品库继续压缩业务无关文字
- [x] 商品详情支持 V2 回退查询
- [x] 商品库列表页默认优先切到 PostgreSQL
- [x] 旧图片代理路由兼容 PostgreSQL 归档图
- [x] 前端显示当前商品源状态（V2 / 上传快照 / Legacy）
- [x] 历史页主读已切到 PostgreSQL（列表 / 详情 / 统计优先走 V2）

---

## H. 后续优先级

1. 商城下架 / 删除策略、断点批次记录和失败项重跑
2. 图搜图上线前核心回归、反馈精排和缓存观察
3. 历史页 / 词库 / 模板规则更多读写链路切 PostgreSQL
4. Redis 队列化长任务与异步状态回传
5. 更细的商城增量抓取指纹、删除/下架策略和对账机制

---

## I. 后续完整任务表（按执行顺序）

| 优先级 | 模块 | 任务 | 状态 | 说明 |
|---|---|---|---|---|
| P0 | 工程规范 | Windows / PowerShell 5.1 编码规则写入全局记忆文件 | [x] | 已写入全局 `C:\Users\30431\.codex\AGENTS.md`；`PROJECT_MEMORY.md` 只是项目级 |
| P0 | 工程规范 | 仓库文本统一 UTF-8 + LF | [x] | 已加 `.editorconfig` / `.gitattributes` |
| P1 | 商品同步 | 上传商品库后的差异报告 | [x] | 已输出新增 / 更新 / 无变化 / 旧图待处理统计和样例 |
| P1 | 商品同步 | 同步失败重试机制 | [x] | 单行失败会重试并记录失败样例，不再轻易拖垮整批同步 |
| P1 | 商品同步 | 增量同步策略 | [x] | 第一版完成：未变化行跳过 product / variant / image 无意义写入 |
| P1 | 商品同步 | Playwright 商城抓取同步源 | [x] | 已有第一版：网络 JSON 捕获 + DOM 商品卡片兜底 + 手动按钮同步 |
| P1 | 商品同步 | 商城抓取预检 / dry-run | [x] | 不写库即可检查页面、登录态、候选数量、字段样例和预计差异 |
| P1 | 商品同步 | 商城抓取登录态 / 选择器实战校准 | [x] | 已校准 `Product/ProductList`、本地登录态、`#productList` 与 `dinghuovip_product_list` 适配器 |
| P1 | 商品同步 | 商城抓取分页增强 | [x] | 已能跟随 `下一页` 链接，实测 2 页正常 |
| P1 | 商品同步 | 商品详情页补图 | [x] | 已支持 `fetch_detail_images`，实测 1 个详情页补 4 张图 |
| P1 | 商品同步 | 商城抓取后台任务入口 | [x] | 已新增 `app.tasks.catalog.scrape_mall_sync` 与 Flask job API，商品库页轮询任务状态 |
| P1 | 商品同步 | 全量抓取限速 / 断点续抓 | [x] | 已支持小批量 / 全量、页间 delay、详情页 delay、checkpoint 与 resume |
| P1 | 商品同步 | 断点批次记录 / 失败项重跑 | [x] | 已支持 `rerun_urls / failed_page_urls`，商品库最近批次可一键重跑失败页 |
| P1 | 商品同步 | 下架 / 删除策略 | [ ] | 疑似下架雏形已完成：只写 `source_payload.mall_sync`，商品库已可按商城状态筛选；复核/正式下架待做 |
| P1 | 商品同步 | 同步任务状态查询增强 | [x] | 已返回最近商城同步任务，并在商品库用轻量 chip 展示批次、页数、异常、疑似下架 |
| P2 | PostgreSQL 收口 | 历史页切 PostgreSQL | [x] | 当前列表 / 详情 / 统计优先走 PostgreSQL V2，SQLite 继续保留回退与兼容写入 |
| P2 | PostgreSQL 收口 | 词库读写切 PostgreSQL | [x] | 已完成 PostgreSQL 主读写，JSON 保留为双写回退，不再只依赖主 JSON 写入 |
| P2 | PostgreSQL 收口 | 模板规则读写切 PostgreSQL | [x] | 已完成 PostgreSQL 主读写，JSON 保留为双写回退，接口结构保持 `{templates:[...]}` 兼容 |
| P2 | PostgreSQL 收口 | 清理剩余 legacy 商品读路径 | [ ] | 把商品检索、详情、图片、反馈统一收口到 PostgreSQL |
| P2 | 报价台 | 继续压缩无关文案，提升业务信息密度 | [x] | 首页、报价台、商品库、模板页、历史页、词库页已继续减字，业务页只保留必要状态与动作 |
| P2 | 报价台 | 左右栏滚动体验继续精修 | [ ] | 继续检查 sticky 区域高度、不同屏宽滚动优先级 |
| P2 | 报价台 | 候选视图继续优化标准 / 紧凑模式 | [ ] | 再压缩说明文案、保留图片、价格、勾选动作 |
| P2 | 报价台 | 首页上传后切到报价台紧凑布局 | [x] | 已同步 `data-route=quotes`，避免按首页样式渲染大块遮挡 |
| P2 | 报价台 | 列映射改为报价台内嵌确认 | [x] | 上传成功后直接进 `/quotes`，不再先卡首页大模态 |
| P2 | 报价台 | 左列独立滚动 | [x] | 鼠标停留左列即可滚动左列内容 |
| P2 | 报价台 | 候选图片区首屏优先加载 | [x] | 报价页图片改成更积极加载，减少首屏空图误判 |
| P2 | 商品库 | 默认优先展示有图商品 | [x] | 已按有图优先排序，并修正图片脚本缓存版本 |
| P2 | 商品库 | 最近商城同步历史轻量入口 | [x] | 已展示最近批次、失败页、差异摘要，并兼容失败页重跑按钮 |
| P2 | 商品库 | 继续精简商品库业务文案 | [x] | 已继续裁掉页头副标题和筛选区多余提示 |
| P2 | 启动链路 | 5000 端口统一改为 `run_server.py --port 5000` | [x] | 避免根目录 `app.py` 与 `backend/app` 同名遮蔽，保证 V2 PostgreSQL 链路稳定生效 |
| P3 | 图搜图 | 512 维向量存储预留 | [x] | 已新增 `embedding_vector_512 vector(512)` 与 HNSW 索引 |
| P3 | 图搜图 | 第二代视觉 embedding（CLIP / 更强 provider） | [x] | 已接入 `torch 2.5.1+cu121` / open_clip_torch，RTX 4060 GPU 验证可用 |
| P3 | 图搜图 | 全量 CLIP 向量生成 | [x] | 首轮全量已完成：`clip_local / openclip_vit_b_32_512d = 3300 / 3300`，`pending_assets = 0`；后续转为新品增量补跑 |
| P3 | 图搜图 | 前端 provider 切换 | [x] | 报价台以图识图已支持“快速图搜 / 智能 CLIP”切换 |
| P3 | 图搜图 | embedding provider 状态化 | [x] | 已可查看 local_hash / clip_local 可用性、维度和待生成数量 |
| P3 | 图搜图 | 生成脚本 provider 参数化 | [x] | 已支持 `--provider / --model-name`，CLIP 未就绪时清晰提示 |
| P3 | 图搜图 | Celery embedding 任务入口 | [x] | 已新增 `app.tasks.embedding.generate_image_embeddings` 与 FastAPI 任务 API |
| P3 | 图搜图 | Flask embedding job 桥接 API | [x] | 已新增 `/api/catalog/image_embedding_jobs` 与状态查询 |
| P3 | 图搜图 | 前端 embedding 任务面板 | [x] | 商品库页已显示快速 / CLIP ready-pending，并可提交每批 20 张的 CLIP 后台任务 |
| P3 | 图搜图 | 报价台支持粘贴图片 / 拍照相册图搜 | [x] | 已支持按钮读取剪贴板、Ctrl+V 粘贴、移动端 `capture` 上传 |
| P3 | 图搜图 | 商品库最小图搜入口 | [x] | 已新增“图搜商品 / 粘贴图片”入口和 `/api/catalog/search_by_image` 通用桥接接口 |
| P3 | 图搜图 | 历史反馈精排 | [x] | 已完成第一版：按 `MatchFeedback.action='select'` 聚合确认次数与权重，对命中的 `product_id` 做保守加分 |
| P3 | 图搜图 | 拍照 / 粘贴图片入口增强 | [ ] | 增加拖拽、失败提示、重复上传去抖和移动端体验检查 |
| P3 | 图搜图 | 图搜图结果缓存 | [x] | 已完成第一版：按图片 bytes sha256 + provider / model / top_k / query 条件缓存最终响应，TTL 6 小时 |
| P4 | 架构升级 | Redis 接入任务状态 / 缓存 | [ ] | 热门搜索、图搜图缓存、任务进度 |
| P4 | 架构升级 | Celery / Worker 长任务化 | [ ] | 同步、向量生成、批处理后台化 |
| P4 | 架构升级 | React + TypeScript 新前端工作台 | [ ] | 为长期可维护性做准备 |
| P4 | 架构升级 | API 契约与类型收敛 | [ ] | 前后端长期协作基础 |
| P5 | 运维 | GitHub Release 说明 | [ ] | 完善版本治理 |
| P5 | 运维 | PostgreSQL / 图片归档备份恢复演练 | [ ] | 真正可回退 |
| P5 | 运维 | V2 上线前压测与性能基线 | [ ] | 为后续重构提供数据 |

---

## J. 下一轮建议直接开工的 9 个任务

### P1：先稳住当前可用版

- [x] README / VERSION / CHANGELOG / 任务清单继续和实际行为对齐
- [ ] 给当前精修版打可识别 tag，并写 GitHub Release 说明
- [ ] 商品库同步 runbook：预检、抓取、失败页重跑、断点续抓形成固定流程

### P2：继续收口数据主链

- [ ] 清理剩余 legacy 商品读路径
- [ ] 补 PostgreSQL / JSON 回退校验清单
- [ ] 历史 / 词库 / 模板做一次收口回归记录

### P3：让图搜图真正进入生产可用

- [ ] CLIP 新品增量补跑策略
- [x] 图搜图缓存方案（Redis key / TTL / 命中策略）
- [x] 历史确认反馈精排第一版
