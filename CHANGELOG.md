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

### 当前重点

1. 根据真实商城页面校准起始 URL、登录态、分页和选择器
2. 继续增强图搜图的召回 + 精排链路
3. 继续把 legacy JSON 读路径往 PostgreSQL 收口
4. 建立更细的商城增量抓取指纹与删除 / 下架策略
5. 为后续 React / TypeScript 重构打基础
