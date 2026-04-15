# 备份与恢复手册

这份文档用来说明当前项目怎么做 **可回退备份、数据恢复、数据库维护**。

---

## 1. 需要备份的内容

### 工作区文件

- `data/`
- `output/`
- `backend/storage/image_archive/`
- `.env` / 本地配置文件（如果有）

### Git 版本点

- 稳定分支：`stable/v0.9-quote-workbench`
- 升级分支：`next/v2-architecture-upgrade`
- 稳定标签：`v0.9.0`

### PostgreSQL

数据库名：`saizheng_quote_v2`

---

## 2. 推荐备份目录

```text
D:\A赛正\project-backups\saizheng-quote-workspace\
```

建议按日期建目录，例如：

```text
D:\A赛正\project-backups\saizheng-quote-workspace\2026-04-16_before-v2-catalog-cutover
```

---

## 3. 文件备份

```powershell
$backupRoot = "D:\A赛正\project-backups\saizheng-quote-workspace\2026-04-16_before-v2-catalog-cutover"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
Copy-Item .\data $backupRoot\data -Recurse -Force
Copy-Item .\output $backupRoot\output -Recurse -Force
Copy-Item .\backend\storage\image_archive $backupRoot\image_archive -Recurse -Force
```

---

## 4. PostgreSQL 备份

### 导出

```powershell
pg_dump -h 127.0.0.1 -U postgres -d saizheng_quote_v2 -Fc -f D:\A赛正\project-backups\saizheng-quote-workspace\2026-04-16_before-v2-catalog-cutover\saizheng_quote_v2.dump
```

### 恢复

```powershell
pg_restore -h 127.0.0.1 -U postgres -d saizheng_quote_v2 --clean --if-exists D:\A赛正\project-backups\saizheng-quote-workspace\2026-04-16_before-v2-catalog-cutover\saizheng_quote_v2.dump
```

---

## 5. Git 回退

### 回到稳定标签

```powershell
git checkout v0.9.0
```

### 回到稳定分支

```powershell
git checkout stable/v0.9-quote-workbench
```

### 回到当前升级分支

```powershell
git checkout next/v2-architecture-upgrade
```

---

## 6. Legacy 数据恢复

如果只是回退 legacy 工作台，可以直接恢复：

- `data/`
- `output/`

例如：

```powershell
Copy-Item "D:\A赛正\project-backups\saizheng-quote-workspace\2026-04-16_before-v2-catalog-cutover\data\*" .\data\ -Recurse -Force
Copy-Item "D:\A赛正\project-backups\saizheng-quote-workspace\2026-04-16_before-v2-catalog-cutover\output\*" .\output\ -Recurse -Force
```

---

## 7. V2 图片归档恢复

```powershell
Copy-Item "D:\A赛正\project-backups\saizheng-quote-workspace\2026-04-16_before-v2-catalog-cutover\image_archive\*" .\backend\storage\image_archive\ -Recurse -Force
```

---

## 8. PostgreSQL 索引维护

如果手动同步过程中遇到索引损坏或唯一索引异常，可执行：

```sql
REINDEX INDEX ix_products_normalized_name;
REINDEX INDEX uq_products_source_external_product;
REINDEX TABLE products;
```

这三个动作已经在当前库上验证过，能处理一次真实出现的索引异常场景。

---

## 9. 最小恢复顺序

建议顺序：

1. 切回正确的 Git 分支 / 标签
2. 恢复 `data/`
3. 恢复 PostgreSQL dump
4. 恢复图片归档目录
5. 启动 Flask / FastAPI 做功能验证
