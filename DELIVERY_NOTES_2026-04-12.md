# 赛正报价工作台交付说明

交付日期：2026-04-12

## 本次交付重点

- 整站视觉语言升级为双主题工作台
  - Light：Pearl Ledger
  - Dark：Obsidian Control
- 完成多页面重构与统一设计系统
  - `/`
  - `/templates`
  - `/quotes`
  - `/catalog`
  - `/history`
  - `/synonyms`
- 报价页重构为单焦点决策流
  - 空态 landing
  - 有数据态 summary / rail / stream / inspector
  - 导出前收口逻辑
- 导出相关模态框高级化
  - 导出报价单
  - 批量价格调整
  - 供应商价格对比
- 完成桌面端与移动端收口

## 当前访问地址

- 本地服务：`http://127.0.0.1:5000`

## 推荐启动方式

### 方式 1：直接启动 Flask

```powershell
cd "D:\A赛正\完整导出的商品信息\claudecode-报价系统"
python app.py
```

### 方式 2：已有辅助脚本

```powershell
cd "D:\A赛正\完整导出的商品信息\claudecode-报价系统"
powershell -ExecutionPolicy Bypass -File .\start_server.ps1
```

> 注意：`run_server.py` 走的是 `8080`，当前主工作流验证使用的是 `5000`。

## 关键资源版本

- `templates/index.html`
- `static/css/workspace_reboot.css?v=20260412i`
- `static/js/match_workbench_override.js?v=20260412b`

## 已完成验证

- 全站主页面 smoke 回归
- quotes 空态 / 有数据态回归
- light / dark 双主题截图验证
- 核心模态框截图验证
- 移动端窄屏回归
- quotes loaded 态控制台错误：`0`
- 主页面 smoke 控制台错误：`0`

## 关键截图

位于：

```text
output/playwright/
```

重点可看：

- `dashboard-final.png`
- `dashboard-dark-final.png`
- `templates-final.png`
- `quotes-empty-final.png`
- `quotes-loaded-after-polish.png`
- `quotes-loaded-dark-after-polish.png`
- `export-modal-after-polish.png`
- `export-modal-dark-after-polish.png`
- `batch-adjust-after-polish.png`
- `price-compare-after-polish.png`
- `dashboard-mobile-final.png`
- `templates-mobile-final-v3.png`
- `quotes-mobile-loaded-final-v3.png`

## 交付状态

当前可视为：

- 可启动
- 可演示
- 可交付

## 建议演示顺序

1. 打开 `/`
2. 切换 `/templates`
3. 切换 `/quotes`
4. 展示空态 landing
5. 注入或加载匹配结果后展示有数据态工作流
6. 打开导出模态框
7. 演示批量调价与价格对比
8. 最后切换 dark theme
