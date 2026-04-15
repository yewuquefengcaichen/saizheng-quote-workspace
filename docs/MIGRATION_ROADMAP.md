# V2 迁移路线图

## Phase 0：冻结稳定版

- 稳定版分支与标签固定
- README / 版本治理 / 回退说明写清楚

## Phase 1：基础设施

- FastAPI / PostgreSQL / Alembic / Redis / Celery 骨架
- 环境变量与健康检查

## Phase 2：商品数据迁移

- `products.json` -> PostgreSQL
- 品牌 / 分类 / 供应商归一化
- 导入报告与抽样校验

## Phase 3：规则与历史迁移

- 同义词、模板规则、历史报价、反馈进入 PostgreSQL

## Phase 4：图片资产化

- 图片归档
- 建 `image_assets` / `image_embeddings`
- 全量补齐 `asset_id / sha256 / phash / dhash`

## Phase 5：图搜图能力落地

- pgvector 向量检索
- Flask 报价台桥接图搜图
- 上传图片 -> 候选返回 -> 回填闭环
- 加入第一轮 rerank

## Phase 6：同步链路升级

- 手动同步 `products.json` -> PostgreSQL
- 记录 `sync_jobs / sync_job_logs`
- 后续演进为 Playwright 商城抓取同步

## Phase 7：工作台逐步切库

- 先切报价台高价值链路
- 再切商品库列表、历史页、规则页
- 最后再考虑 React 新前端全面替换
