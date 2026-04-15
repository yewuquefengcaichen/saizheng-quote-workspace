# V2 升级任务清单

> 这份清单只记录现在真实有效的升级工作，不再保留乱码内容。

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
- [x] 同步结果写入 `sync_jobs / sync_job_logs`
- [ ] 增加差异同步统计
- [ ] 增加失败重试
- [ ] 增加 Playwright 商城抓取同步源

---

## G. 当前工作台桥接

- [x] 报价项文字搜可用于人工选品
- [x] 报价项以图识图可回填当前项
- [x] 商品详情支持 V2 回退查询
- [ ] 商品库列表页全面切到 PostgreSQL
- [ ] 历史页全面切到 PostgreSQL

---

## H. 后续优先级

1. 商品库列表页改为 PostgreSQL 读路径
2. 商城手动同步增加差异报告
3. 图搜图升级 CLIP / 更强视觉模型
4. React + TypeScript 新前端工作台
5. Redis 队列化长任务与异步状态回传
