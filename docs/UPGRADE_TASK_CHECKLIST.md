# V2 升级任务清单

> 这份清单只记录现在真实有效的升级工作，不再保留乱码内容。

> 状态说明：`[x]` 已完成、`[ ]` 待做。

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
- [ ] 升级第二代视觉 embedding（CLIP / 更强 provider）
- [ ] 接入历史反馈精排

---

## F. 商品同步

- [x] 保留“上传商品库 -> 刷新 `products.json`”旧链路
- [x] 新增手动“同步 V2”入口
- [x] 上传商品库后可选“立即同步 V2”
- [x] 同步结果写入 `sync_jobs / sync_job_logs`
- [ ] 增加差异同步统计
- [ ] 增加失败重试
- [ ] 增加增量同步策略（避免每次全量刷新）
- [ ] 增加 Playwright 商城抓取同步源

---

## G. 当前工作台桥接

- [x] 报价主匹配优先读取 PostgreSQL 商品快照
- [x] 报价项文字搜可用于人工选品
- [x] 报价项以图识图可回填当前项
- [x] 商品详情支持 V2 回退查询
- [x] 商品库列表页默认优先切到 PostgreSQL
- [x] 旧图片代理路由兼容 PostgreSQL 归档图
- [x] 前端显示当前商品源状态（V2 / 上传快照 / Legacy）
- [ ] 历史页全面切到 PostgreSQL

---

## H. 后续优先级

1. 商城同步增加差异报告
2. 同步失败重试 + 增量同步
3. 图搜图升级 CLIP / 更强视觉模型
4. 历史页 / 更多读写链路切 PostgreSQL
5. Redis 队列化长任务与异步状态回传

---

## I. 后续完整任务表（按执行顺序）

| 优先级 | 模块 | 任务 | 状态 | 说明 |
|---|---|---|---|---|
| P0 | 工程规范 | Windows / PowerShell 5.1 编码规则写入全局记忆文件 | [x] | 已写入 `PROJECT_MEMORY.md` |
| P0 | 工程规范 | 仓库文本统一 UTF-8 + LF | [x] | 已加 `.editorconfig` / `.gitattributes` |
| P1 | 商品同步 | 上传商品库后的差异报告 | [ ] | 输出新增 / 更新 / 跳过 / 失败明细 |
| P1 | 商品同步 | 同步失败重试机制 | [ ] | 为长任务与异常恢复打基础 |
| P1 | 商品同步 | 增量同步策略 | [ ] | 避免频繁全量刷新 |
| P1 | 商品同步 | Playwright 商城抓取同步源 | [ ] | 商城无官方 API 时的抓取兜底 |
| P1 | 商品同步 | 同步任务状态查询增强 | [ ] | 前端展示进度、日志、异常项 |
| P2 | PostgreSQL 收口 | 历史页切 PostgreSQL | [ ] | 逐步摆脱 `quote_history.db` |
| P2 | PostgreSQL 收口 | 词库 / 模板规则读写逐步切 PostgreSQL | [ ] | 减少 JSON 依赖 |
| P2 | PostgreSQL 收口 | 清理剩余 legacy 商品读路径 | [ ] | 最终让 JSON 退居备份 / 导入中间态 |
| P2 | 报价台 | 继续压缩无关文案，提升业务信息密度 | [ ] | 只保留必要操作信息 |
| P2 | 报价台 | 左右栏滚动体验继续精修 | [ ] | 鼠标停留区域即独立滚动 |
| P2 | 报价台 | 候选视图继续优化标准 / 紧凑模式 | [ ] | 提升大量候选时效率 |
| P3 | 图搜图 | 第二代视觉 embedding（CLIP / 更强 provider） | [ ] | 提高以图识图准确率 |
| P3 | 图搜图 | 历史反馈精排 | [ ] | 把已确认行为用于 rerank |
| P3 | 图搜图 | 拍照 / 粘贴图片入口增强 | [ ] | 更接近真实业务用法 |
| P3 | 图搜图 | 图搜图结果缓存 | [ ] | 为性能优化做准备 |
| P4 | 架构升级 | Redis 接入任务状态 / 缓存 | [ ] | 热门搜索、图搜图缓存、任务进度 |
| P4 | 架构升级 | Celery / Worker 长任务化 | [ ] | 同步、向量生成、批处理后台化 |
| P4 | 架构升级 | React + TypeScript 新前端工作台 | [ ] | 为长期可维护性做准备 |
| P4 | 架构升级 | API 契约与类型收敛 | [ ] | 前后端长期协作基础 |
| P5 | 运维 | GitHub Release 说明 | [ ] | 完善版本治理 |
| P5 | 运维 | PostgreSQL / 图片归档备份恢复演练 | [ ] | 真正可回退 |
| P5 | 运维 | V2 上线前压测与性能基线 | [ ] | 为后续重构提供数据 |
