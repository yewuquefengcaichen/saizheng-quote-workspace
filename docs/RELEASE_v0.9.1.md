# v0.9.1 · 报价台精修版（上线前最后收口 Release 草稿）

这份草稿用于 GitHub Release，目标是把“可用范围、冻结标准、回退方式、发布时间计划”一次写清楚。

---

## 1. 本版定位

`v0.9.1` 是“可用精修版 + 上线前最后收口版”，不是最终架构完成版。

本版重点：
- 报价台工作流精修（上传后直达 `/quotes`、页内映射、左右高密度选品）
- 数据收口推进（历史页主读、词库主读写）
- 图搜图生产化第一版（Redis 缓存 + 历史反馈精排 + CLIP 全量）
- 当前阶段：**v0.9.1 上线前最后收口**

---

## 2. 当前已完成能力

- 首页上传报价后直接进入报价台，不再被首页阻塞。
- 列映射确认改为报价台内嵌流程。
- 词库已切 PostgreSQL 主读写，保留 JSON 双写回退。
- 模板已切 PostgreSQL 主读写，保留 JSON 双写回退。
- 历史页接口主读 PostgreSQL。
- 图搜图接入 Redis 查询缓存（TTL 6 小时）。
- 图搜图接入历史反馈精排第一版。
- CLIP 全量向量已完成：`clip_local / openclip_vit_b_32_512d = 3300 / 3300`，`pending_assets = 0`。

---

## 3. 冻结门槛（Release 前必须满足）

1. CLIP 全量状态确认：`clip_local / openclip_vit_b_32_512d = 3300 / 3300`，`pending_assets = 0`。
2. 回归检查通过：
   - 报价台主流程
   - 词库增删改查
   - 模板增删改查
   - 历史页列表/统计
   - 图搜图查询
3. 文档同步完成：
   - `README.md`
   - `CHANGELOG.md`
   - `docs/PROJECT_PROGRESS.md`
   - `docs/VERSION_POLICY.md`
   - `docs/PHASE_PLAN_v0.9.1.md`
4. 版本冻结与回退锚点确认完成：`v0.9.1` tag、Release 说明、push 顺序可执行。

---

## 4. 回退与锚点

- 老稳定点：`v0.9.0`
- 本轮冻结点：`v0.9.1`
- 稳定线：`stable/v0.9-quote-workbench`
- 升级线：`next/v2-architecture-upgrade`

常用命令：

```powershell
git checkout v0.9.0
git checkout v0.9.1
git checkout stable/v0.9-quote-workbench
git checkout next/v2-architecture-upgrade
```

---

## 5. 建议 commit / tag

建议 commit（示例）：

```text
feat(模板): 模板读写切换到 PostgreSQL 主链并保留 JSON 双写回退
feat(图搜图): 接入 Redis 查询缓存与历史反馈精排第一版
docs(发布): 完善 v0.9.1 冻结条件、工期与回退策略
```

建议 tag：

```text
v0.9.1
```

---

## 6. push 执行顺序

```powershell
git status --short --branch
git add app.py backend/app/api/routes/image_search.py backend/app/services/image_embedding.py docs README.md CHANGELOG.md
git commit -m "feat(收口): 完成模板收口并冻结 v0.9.1 发布材料"
git push origin next/v2-architecture-upgrade
git tag -a v0.9.1 -m "v0.9.1 报价台精修版（数据收口+图搜图第一版）"
git push origin v0.9.1
git ls-remote --tags origin v0.9.1
```

---

## 7. 工期拆分（可执行）

详见：`docs/PHASE_PLAN_v0.9.1.md`

简版：
- `0.5 天`：核心回归 + 文档对齐
- `0.5 天`：版本冻结 + commit / tag / push + 上线准备
- `1~2 天`：若回归有阻塞，补兼容方案、补验证、再执行冻结

---

## 8. Release 标题与简介

标题：

```text
v0.9.1 · 报价台精修版
```

简介：

```text
报价主流程已精修为高密度工作流，历史与词库收口到 PostgreSQL 主链，图搜图接入缓存与反馈精排第一版，并形成可回退的阶段冻结锚点。
```
