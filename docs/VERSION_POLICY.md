# 版本冻结与回退策略（v0.9.1）

这份文档只回答 5 件事：
1. 这轮什么时候可以冻结
2. 冻结后回退锚点是什么
3. commit / tag 怎么命名
4. push 按什么顺序执行
5. 如果后续继续升级，分支怎么走

---

## 1. 当前版本锚点

| 名称 | 类型 | 作用 |
| --- | --- | --- |
| `stable/v0.9-quote-workbench` | 分支 | 稳定工作线（可日常使用） |
| `next/v2-architecture-upgrade` | 分支 | 升级开发线（数据库 / 图搜图 / 架构） |
| `v0.9.0` | Tag | 已确认可回退的老稳定点 |
| `v0.9.1` | Tag（本轮目标） | 本轮精修+收口后的新回退点 |

---

## 2. v0.9.1 冻结条件（必须全部满足）

1. 模板模块保持 PostgreSQL 主读写可用（当前已完成）。
2. 历史页、词库与模板链路保持可用（当前已是 PostgreSQL 主链）。
3. 图搜图缓存与反馈精排第一版可用（当前已完成）。
4. CLIP 全量向量已完成：`clip_local / openclip_vit_b_32_512d = 3300 / 3300`，`pending_assets = 0`。
5. 当前阶段统一定义为：**v0.9.1 上线前最后收口**。
6. 文档齐套：`README.md`、`CHANGELOG.md`、`docs/PROJECT_PROGRESS.md`、`docs/RELEASE_v0.9.1.md`。
7. 本地基础回归通过（至少：报价台、历史、词库、模板、图搜图查询）。

---

## 3. 回退锚点

### 回到老稳定点
```powershell
git checkout v0.9.0
```

### 回到本轮冻结点（打完 tag 后）
```powershell
git checkout v0.9.1
```

### 回到稳定工作线
```powershell
git checkout stable/v0.9-quote-workbench
```

### 回到升级开发线
```powershell
git checkout next/v2-architecture-upgrade
```

---

## 4. commit / tag 命名规范

### commit 格式
```text
类型(范围): 中文说明
```

### 本轮建议 commit 名称
```text
feat(模板): 模板读写切换到 PostgreSQL 主链并保留 JSON 双写回退
feat(图搜图): 接入 Redis 查询缓存与历史反馈精排第一版
docs(发布): 完善 v0.9.1 冻结条件、工期与回退策略
```

### 本轮建议 tag
```text
v0.9.1
```

如果需要更细标识（可选）：
```text
v0.9.1-quote-workbench
```

---

## 5. 推荐 push 顺序（非交互）

1. 确认分支与变更：
```powershell
git status --short --branch
```

2. 提交代码与文档：
```powershell
git add app.py backend/app/api/routes/image_search.py backend/app/services/image_embedding.py docs README.md CHANGELOG.md
git commit -m "feat(收口): 完成模板收口并冻结 v0.9.1 发布材料"
```

3. 推送分支：
```powershell
git push origin next/v2-architecture-upgrade
```

4. 打 tag：
```powershell
git tag -a v0.9.1 -m "v0.9.1 报价台精修版（数据收口+图搜图第一版）"
```

5. 推送 tag：
```powershell
git push origin v0.9.1
```

6. 最后验证远端锚点：
```powershell
git ls-remote --tags origin v0.9.1
```

---

## 6. 后续分支策略

- `stable/v0.9-quote-workbench`：只接收稳定修复，不做大改造。
- `next/v2-architecture-upgrade`：继续推进 V2 架构升级。
- 下一个阶段开始前，先从 `next/...` 拉阶段分支，避免直接在稳定线做高风险改动。
