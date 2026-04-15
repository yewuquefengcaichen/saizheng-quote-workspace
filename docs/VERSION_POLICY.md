# 版本与 Git 策略

这份文档说明赛正报价工作台当前怎么命名分支、怎么打 tag、怎么写提交信息。

---

## 1. 分支策略

### 稳定分支

```text
stable/v0.9-quote-workbench
```

用途：

- 保存当前可直接回退、可继续工作的稳定版本
- 只接收必要修复
- 对应稳定标签 `v0.9.0`

### 升级主分支

```text
next/v2-architecture-upgrade
```

用途：

- 承接 PostgreSQL / pgvector / 图搜图 / 新前端架构升级
- 允许较大改动
- 作为当前开发主线

### 临时功能分支

```text
feat/中文短名-英文关键词
fix/中文短名-英文关键词
refactor/中文短名-英文关键词
```

示例：

```text
feat/商品库切pg-catalog-pg
fix/修复乱码-fix-garbled-docs
refactor/报价台分栏-refactor-workbench-layout
```

---

## 2. Tag 策略

```text
v主版本.次版本.修订号
```

示例：

- `v0.9.0`：稳定报价工作台基线
- `v1.x`：Flask 工作台增强版本
- `v2.x`：新架构正式版

---

## 3. 提交信息策略

建议格式：

```text
类型(范围): 中文说明
```

常用类型：

- `feat`
- `fix`
- `docs`
- `refactor`
- `perf`
- `test`
- `chore`

示例：

```text
feat(商品库): 商品库列表页优先切到 PostgreSQL
fix(乱码): 重写损坏文档并修复样例报价单
docs(README): 更新当前真实架构与数据存放说明
```

---

## 4. GitHub 展示建议

- 分支名可以中英混合，但要短
- 提交说明以中文为主
- Release 说明写清楚版本能力、用途和回退方式
- 重要节点必须打 tag

---

## 5. 当前建议

- 把 `v0.9.0` 作为稳定回退点长期保留
- 所有架构升级继续放在 `next/v2-architecture-upgrade`
- 每一轮重要改动都写清楚中文提交说明
- 每做完一个可回看的阶段，就补一次 changelog / README / docs
