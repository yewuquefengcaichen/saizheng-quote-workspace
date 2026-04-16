# 商城抓取同步说明

## 当前定位

商城没有官方 API 时，先用 Playwright 做一条可控的同步兜底链路：

1. 打开配置好的商城商品页
2. 优先按站点适配器解析真实 DOM；没有适配器时再捕获页面请求返回的 JSON
3. 如果没有可用 JSON，再从通用 DOM 商品卡片提取
4. 转成当前商品同步需要的标准字段
5. 写入 V2 PostgreSQL，同步结果进入 `sync_jobs / sync_job_logs`

## 前端入口

商品库页：

- `同步 V2`：把当前 `data/products.json` 同步进 PostgreSQL
- `抓商城`：用 Playwright 从商城页面抓取后同步进 PostgreSQL
- `预检商城`：只抓取和 dry-run，不写库，用来先确认字段、登录态和预计差异

## 后端入口

Flask 桥接接口：

```text
POST /api/catalog/sync_from_mall
POST /api/catalog/scrape_mall_preview
```

其中：

- `sync_from_mall`：抓取并同步写入 V2 PostgreSQL
- `scrape_mall_preview`：只预检，不写库；用于确认登录态、分页、字段是否正确

首次使用前确保安装浏览器运行时：

```powershell
pip install playwright
python -m playwright install chromium
```

默认读取配置：

```text
SAIZHENG_MALL_SCRAPE_START_URL
SAIZHENG_MALL_SCRAPE_PAGE_URL_TEMPLATE
SAIZHENG_MALL_SCRAPE_STORAGE_STATE_PATH
SAIZHENG_MALL_SCRAPE_HEADLESS
SAIZHENG_MALL_SCRAPE_MAX_PAGES
SAIZHENG_MALL_SCRAPE_PAGE_TIMEOUT_MS
SAIZHENG_MALL_SCRAPE_SITE_ADAPTER
SAIZHENG_MALL_SCRAPE_DOM_TABLE_SELECTOR
SAIZHENG_MALL_SCRAPE_NETWORK_INCLUDE_PATTERNS
SAIZHENG_MALL_SCRAPE_NETWORK_EXCLUDE_PATTERNS
```

请求体也可以临时覆盖配置：

```json
{
  "start_url": "https://你的商城商品列表页",
  "page_url_template": "https://你的商城商品列表页?page={page}",
  "max_pages": 3,
  "storage_state_path": "backend/storage/mall-auth/state.json",
  "site_adapter": "dinghuovip_product_list",
  "dom_table_selector": "#productList",
  "network_include_patterns": ["/Product/"],
  "network_exclude_patterns": ["/Notice/", "/ManuSysNotice"],
  "field_map": {
    "code": ["ProductNo", "SkuNo"],
    "name": ["ProductTitle"],
    "market_price": ["SellPrice"]
  }
}
```

## 登录态

如果商城需要登录，后续建议用 Playwright 保存登录态：

```powershell
python -m playwright codegen --save-storage=backend/storage/mall-auth/state.json https://你的商城地址
```

然后在 `.env` 里配置：

```text
SAIZHENG_MALL_SCRAPE_STORAGE_STATE_PATH=backend/storage/mall-auth/state.json
```

注意：

- 登录态文件放在 `backend/storage/mall-auth/`，该目录已被 `.gitignore` 忽略。
- 不要把商城账号、密码、Cookie、登录态 JSON 写进 README、提交记录或公开文档。

## 赛正 dinghuovip 已校准参数

真实商品列表页：

```text
https://sz.dinghuovip.com/Product/ProductList
```

推荐预检请求体：

```json
{
  "start_url": "https://sz.dinghuovip.com/Product/ProductList",
  "max_pages": 1,
  "headless": true,
  "page_timeout_ms": 30000,
  "storage_state_path": "backend/storage/mall-auth/saizheng-state.json",
  "site_adapter": "dinghuovip_product_list",
  "dom_table_selector": "#productList"
}
```

当前验证结果：

- 页面标题：`商品列表`
- 表格选择器：`#productList`
- 首屏 DOM 商品数：10
- 已避开 `/Notice/` 等通知 JSON 误识别
- 字段已提取：编码、名称、型号、市场价、采购价、供应商、状态、封面图、详情链接
- 列表页图片按 `append_only` 同步，避免只抓到封面时把详情历史图误判为删除

## 当前已经做了什么

- 网络 JSON 自动识别商品字段
- DOM 商品卡片兜底识别
- `dinghuovip_product_list` 站点适配器：专门解析 `#productList` 商品表
- 网络 include / exclude 过滤，避免通知 JSON 被当成商品
- 预检接口，不写库也能看提取数量和差异
- 疑似登录页检测
- 抓不到商品时保存调试截图：`output/playwright/mall-scrape-latest.png`
- 返回受限的 raw payload 样例，方便校准字段名
- 商品字段转成现有 `code / name / model / category / unit / market_price / cost_price / brand / supplier / intro / image_urls / primary_image_url`
- 同步到 V2 PostgreSQL
- 与差异统计、行级重试、未变化跳过写入共用同一套链路

## 还需要实战校准的点

- 分页 URL 模板或下一页按钮选择器
- 是否需要进入商品详情页补齐多张详情图
- 下架 / 删除商品如何表达：只标记 inactive，还是进入人工复核
- 长任务化：抓取、同步、图片归档、embedding 生成应该进入 Redis / Celery 任务队列
