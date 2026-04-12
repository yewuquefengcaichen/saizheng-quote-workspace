# 赛正报价工作台 / Saizheng Quote Workspace

一个基于 Flask 的本地报价工作台项目，覆盖：

- 商品资产库浏览与检索
- 报价项匹配与人工确认
- 模板中心与导出配置
- 历史记录与词库维护
- Light / Dark 双主题工作台

当前版本已经完成一轮整站重构，重点把系统从“功能堆叠页面”升级成“多页面、高级工作台式体验”。

---

## 当前页面

- `/` 总览
- `/templates` 模板中心
- `/quotes` 报价决策台
- `/catalog` 商品资产库
- `/history` 历史记录
- `/synonyms` 词库

---

## 设计重构重点

- 多页面统一设计系统
- Light：Pearl Ledger
- Dark：Obsidian Control
- 报价页改造成单焦点决策流
- 导出 / 调价 / 价格对比模态框高级化
- 响应式与移动端收口

---

## 本地启动

### 方式 1

```powershell
cd "D:\A赛正\完整导出的商品信息\claudecode-报价系统"
python app.py
```

### 方式 2

```powershell
cd "D:\A赛正\完整导出的商品信息\claudecode-报价系统"
.\start_local_5000.bat
```

启动后访问：

```text
http://127.0.0.1:5000
```

---

## 依赖安装

```powershell
pip install -r requirements.txt
```

---

## 当前已完成

- 整站视觉与信息层级重构
- quotes 空态 / 有数据态重构
- 导出流程交付级模态框收口
- 桌面端与移动端 smoke 回归

---

## 后续仍建议继续改进

- 进一步压缩部分页面的信息密度
- 清理历史样式残留与旧 CSS 依赖
- 提升模板中心与报价页的小屏可读性
- 继续梳理数据结构、组件拆分与前端脚本模块化
- 增加更正式的 README、演示文档与部署说明

---

## 交付说明

详见：

```text
DELIVERY_NOTES_2026-04-12.md
```
