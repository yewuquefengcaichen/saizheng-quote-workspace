# 赛正报价工作台

一个基于 **Flask + Jinja2 + 原生 JS/CSS + SQLite/JSON** 的本地报价处理系统，用来完成：

- 商品库导入与检索
- 报价单上传、解析、候选匹配
- 人工确认、人工搜全商城、异常收口
- 批量调价与最终导出
- 历史记录、同义词、说明页管理

---

## 1. 项目定位

这个项目不是传统“后台表格堆满一屏”的报价系统，而是一个围绕 **报价确认效率** 做的工作台：

- 左侧保留原始报价信息和必要动作
- 右侧专门处理候选商品选择
- 已确认项可折叠，减少视觉干扰
- 商品详情走右侧抽屉
- 全商城搜索走弹窗
- 业务页面尽量不塞说明文字，说明统一放说明页 / README

---

## 2. 当前主要页面

- `/`：总览
- `/quotes`：报价工作台
- `/catalog`：商品库
- `/templates`：模板中心
- `/history`：历史记录
- `/synonyms`：同义词 / 词库
- `/guide`：说明页

---

## 3. 技术栈

### 后端

- Python
- Flask
- Waitress（`run_server.py` 用于 8080）

### 数据处理

- pandas
- numpy
- openpyxl
- xlrd
- jieba

### 存储

- SQLite
- JSON

### 前端

- Jinja2 模板
- 原生 JavaScript
- 原生 CSS
- Bootstrap 5
- Bootstrap Icons

### 可选 AI / 扩展能力

- anthropic
- openai
- sentence-transformers
- aiohttp
- pyyaml

### 可选导出 / OCR

- reportlab
- weasyprint
- easyocr（当前依赖里预留，默认可不装）

---

## 4. 数据放在哪里

### 核心数据目录：`data/`

主要数据都在这里。

#### SQLite

- `data/quote_history.db`
  - 报价历史
  - 已确认结果
  - 导出记录 / 历史详情

- `data/ai_cache.db`
  - AI 相关缓存

#### JSON

- `data/products.json`
  - 商品库主数据

- `data/products.last_uploaded.json`
  - 最近一次上传的商品库备份

- `data/parse_templates.json`
  - 智能解析模板配置

- `data/synonyms.json`
  - 同义词词库

- `data/normalization_rules.json`
  - 规格 / 名称规范化规则

### 输出目录：`output/`

这里放运行时输出内容，例如：

- 导出的报价单 / 订货单 / 发货单
- 调试截图
- 中间产物

> 结论：**是的，项目数据确实用了 SQLite，但不是只放 SQLite，商品库和规则类数据同时放在 JSON。**

---

## 5. 目录结构

```text
.
├─ app.py                         # Flask 主入口（5000）
├─ run_server.py                  # Waitress 启动入口（8080）
├─ requirements.txt               # Python 依赖
├─ data/                          # SQLite + JSON 数据
├─ output/                        # 导出与调试产物
├─ static/
│  ├─ css/                        # 工作台样式
│  └─ js/                         # 前端交互逻辑
├─ templates/
│  ├─ index.html                  # 主模板
│  └─ partials/                   # 各页面局部模板
└─ utils/
   ├─ excel_handler.py            # Excel 解析
   ├─ smart_parser.py             # 智能列识别 / 模板学习
   ├─ matcher.py                  # 商品匹配
   ├─ image_handler.py            # 商品图片处理
   ├─ database.py                 # SQLite 读写
   ├─ normalizer.py               # 规格 / 文本规范化
   ├─ ai_service.py               # AI 服务接入
   ├─ ai_matcher.py               # AI 匹配器
   └─ pdf_exporter.py             # PDF 导出
```

---

## 6. 启动方式

### 方式 A：开发运行（5000）

```powershell
cd "D:\A赛正\完整导出的商品信息\claudecode-报价系统"
python app.py
```

访问：

```text
http://127.0.0.1:5000
```

也可以直接：

```powershell
.\start_local_5000.bat
```

### 方式 B：Waitress 运行（8080）

```powershell
cd "D:\A赛正\完整导出的商品信息\claudecode-报价系统"
python run_server.py
```

访问：

```text
http://127.0.0.1:8080
```

---

## 7. 安装依赖

```powershell
pip install -r requirements.txt
```

建议 Python 3.10+。

---

## 8. 报价工作流

### Step 1：准备商品库

先保证 `data/products.json` 有有效商品数据，或通过商品库页面上传。

### Step 2：上传报价单

支持：

- `.xls`
- `.xlsx`
- 图片 OCR（可选）

### Step 3：智能解析

系统会做：

- 表头识别
- 列含义推断
- 模板命中
- 解析结果预览

### Step 4：确认列映射

确认后进入真正报价项提取，并生成候选匹配结果。

### Step 5：进入 `/quotes`

在报价页完成：

- 查看原始报价数据
- 查看候选商品
- 标记无匹配 / 问老板
- 人工搜全商城
- 选择候选并确认
- 已确认项折叠收口

### Step 6：批量调价

支持：

- 百分比加价 / 折扣
- 固定金额加价 / 减价
- 全部项 / 仅已确认项

### Step 7：导出

确认完成后进入导出流程，输出报价单及相关单据。

---

## 9. `/quotes` 当前页面设计要点

本轮已经按高效率报价流做了这些调整：

- 左小右大双栏
- 支持拖拽调整左右宽度
- 支持“标准视图 / 紧凑视图”
- 右侧候选区优先显示商品卡片
- 商品详情使用右侧抽屉
- 全商城搜索使用弹窗
- 已确认项默认可折叠
- 报价页去掉分享入口
- 去掉大量无关说明文案
- 鼠标停在哪块，哪块优先滚动
- 报价页隐藏不必要的悬浮助手入口和顶部右侧杂项工具

页面状态的一部分保存在 `localStorage`，包括：

- 候选视图
- 左右分栏宽度
- 主题 / 局部界面状态

---

## 10. 商品库流程

商品库页主要负责：

- 上传 / 更新商品库
- 查看商品图片
- 搜索名称、品牌、型号、供应商
- 查看商品详情
- 为报价页提供候选基础数据

商品库质量越完整，报价页自动匹配越稳定。

---

## 11. 历史记录与词库

### 历史记录

历史记录保存在：

- `data/quote_history.db`

可用于：

- 回看历史报价
- 复盘已确认结果
- 获取统计信息

### 同义词 / 规范化

词库与规则位于：

- `data/synonyms.json`
- `data/normalization_rules.json`

它们会影响：

- 搜索命中
- 匹配效果
- 文本标准化

---

## 12. 主要后端接口（概览）

常用接口包括：

- `/api/upload_products`
- `/api/upload_quote`
- `/api/smart_parse`
- `/api/confirm_mapping`
- `/api/get_match_results`
- `/api/catalog/search_for_quote`
- `/api/export_quote`
- `/api/get_quote_history`

---

## 13. 常见问题

### 1）项目数据是不是 SQLite？

**部分是。**

- 历史与缓存：SQLite
- 商品库、模板、词库、规则：JSON

### 2）为什么 5000 和 8080 都能启动？

- `app.py`：Flask 开发方式，跑 `5000`
- `run_server.py`：Waitress 方式，跑 `8080`

### 3）为什么我改了页面但浏览器看起来没变化？

可能是缓存。可以：

- 强制刷新浏览器
- 或修改静态资源版本号

### 4）导出文件在哪？

默认在：

```text
output/
```

### 5）商品图片为什么有的是代理地址？

项目会通过图片代理接口统一处理商品图，避免前端直接依赖外部地址。

---

## 14. Git 提交建议

建议提交：

- `templates/`
- `static/css/`
- `static/js/`
- `README.md`
- 必要的 Python 代码

通常不要提交：

- `output/`
- `data/quote_history.db`
- `data/ai_cache.db`
- 临时日志
- 调试截图

当前 `.gitignore` 已经忽略了大部分运行产物。

---

## 15. 本项目还建议继续做的事

如果继续往下做，我建议优先这几项：

1. **把 AI 助手文案和乱码再系统清理一遍**
2. **把 `workspace_reboot.css` 里多轮叠加样式进一步归并**
3. **给 `/quotes` 做更完整的交互验收脚本**
4. **把商品详情抽屉与全商城搜索弹窗再做一次响应式优化**
5. **把解析模板、同义词、规范化规则做更清晰的后台维护入口**
6. **补自动化回归：上传 → 解析 → 确认 → 导出**

---

## 16. 当前结论

这个项目当前真实落地形态可以概括为：

- **后端：Python + Flask**
- **前端：Jinja2 + 原生 JS/CSS + Bootstrap**
- **数据：SQLite + JSON**
- **用途：本地商品库报价处理工作台**
- **核心页面：`/quotes`**

如果你后面要继续扩，我建议优先围绕 **报价确认速度、人工搜索效率、导出闭环** 继续做，不要再把大量说明文案塞回业务页。

---

## V2 升级进度（2026-04-15）

当前仓库已经新增一套 **V2 架构升级底座**，重点不是替换现有稳定版，而是在 `next/v2-architecture-upgrade` 分支上逐步完成：

- FastAPI + PostgreSQL + Redis/Celery 后端底座
- 旧商品、规则、历史报价数据迁移进 PostgreSQL
- 图片归档与去重资产层（`image_assets`）
- 图搜图前置表（`image_embeddings`）

本轮最新进度文档：

- `docs/ARCHITECTURE_V2_PLAN.md`
- `docs/MIGRATION_ROADMAP.md`
- `docs/UPGRADE_TASK_CHECKLIST.md`
- `docs/IMAGE_ARCHIVE_PROGRESS_2026-04-15.md`

如果你要继续推进“拍照识别 / 以图识图 / 新商城同步 / React 新前端”，请优先阅读上面这几份文档。
- 当前已完成全量 `25755` 条商品图片归档，沉淀出 `3300` 个去重图片资产，作为后续图搜图底座。

---

## V2 图搜图进度（2026-04-15）

当前 V2 不只是有图片归档，还已经具备第一版可运行的图搜图能力：

- PostgreSQL 已切到 `pgvector/pgvector:pg17`
- 数据库已启用 `vector` 扩展
- `image_embeddings` 已补 `vector(128)` 向量列
- 已生成 `3300` 条图片向量
- 已新增图片检索 API：`POST /api/v1/image-search/query`
- 已新增归档图片访问 API：`GET /api/v1/image-search/assets/{asset_id}/file`
- 当前稳定版 `/quotes` 报价台也已经桥接这套能力，可直接在“以图识图”里上传图片选 SKU
- Flask 侧桥接接口：
  - `POST /api/catalog/search_by_image_for_quote`
  - `GET /api/catalog/image_asset/<asset_id>/file`

当前向量方案使用：

- `local_hash_embedding`
- `phash_dhash_128d_v1`

这是一版**先跑通架构和链路**的可运行方案；后续可以无缝升级为更强的 CLIP / 视觉语义 embedding，而不需要推翻现有表结构。

详见：

- `docs/IMAGE_VECTOR_SEARCH_PROGRESS_2026-04-15.md`
