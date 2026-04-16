# 商城抓取同步说明

## 当前定位

商城没有官方 API 时，先用 Playwright 做一条可控的同步兜底链路：

1. 打开配置好的商城商品页
2. 优先捕获页面请求返回的 JSON
3. 如果没有可用 JSON，再从 DOM 商品卡片提取
4. 转成当前商品同步需要的标准字段
5. 写入 V2 PostgreSQL，同步结果进入 `sync_jobs / sync_job_logs`

## 前端入口

商品库页：

- `同步 V2`：把当前 `data/products.json` 同步进 PostgreSQL
- `抓商城`：用 Playwright 从商城页面抓取后同步进 PostgreSQL

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
```

请求体也可以临时覆盖配置：

```json
{
  "start_url": "https://你的商城商品列表页",
  "page_url_template": "https://你的商城商品列表页?page={page}",
  "max_pages": 3,
  "storage_state_path": "backend/storage/mall-auth/state.json",
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

## 当前已经做了什么

- 网络 JSON 自动识别商品字段
- DOM 商品卡片兜底识别
- 预检接口，不写库也能看提取数量和差异
- 疑似登录页检测
- 抓不到商品时保存调试截图：`output/playwright/mall-scrape-latest.png`
- 返回受限的 raw payload 样例，方便校准字段名
- 商品字段转成现有 `code / name / model / category / unit / market_price / cost_price / brand / supplier / intro`
- 同步到 V2 PostgreSQL
- 与差异统计、行级重试、未变化跳过写入共用同一套链路

## 还需要实战校准的点

- 真实商品列表页 URL
- 是否需要登录态
- 分页 URL 模板或下一页按钮选择器
- 商品卡片选择器
- 商城实际 JSON 字段命名
