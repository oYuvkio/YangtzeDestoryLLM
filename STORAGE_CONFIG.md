# 项目存储空间配置说明

## 📁 配置概览

本项目已配置使用服务器新增的 80T 存储空间（`/media/data2`），以避免根分区空间不足的问题。

## 🗂️ 目录结构

```
/media/data2/YangtzeDestoryLLM/
├── data/                    # 项目数据目录（2.4G）
│   ├── corpus_for_kg/       # KG构建语料
│   ├── corpus_for_onto/     # 本体构建语料
│   └── ...
├── outputs/                 # 输出结果目录（2.9M）
│   └── cq_pipeline/         # P1-P5流水线输出
├── models_cache/            # 预训练模型缓存
│   ├── transformers/        # HuggingFace模型
│   ├── sentence_transformers/
│   ├── torch/               # PyTorch Hub
│   └── datasets/
└── logs_archive/            # 历史日志归档
```

## 🔗 符号链接

项目工作目录中的 `data/` 和 `outputs/` 已通过符号链接指向新存储：

```bash
~/dev_ops/YangtzeDestoryLLM/data -> /media/data2/YangtzeDestoryLLM/data
~/dev_ops/YangtzeDestoryLLM/outputs -> /media/data2/YangtzeDestoryLLM/outputs
```

**优点**：
- 代码无需修改，路径保持不变
- 自动使用大容量存储
- 备份数据保留在 `data_backup/` 和 `outputs_backup/`

## ⚙️ 环境变量配置

### 每次运行前激活环境变量

```bash
cd ~/dev_ops/YangtzeDestoryLLM
source setup_storage_env.sh
```

这会设置以下环境变量：
- `HF_HOME`: HuggingFace 总缓存目录
- `TRANSFORMERS_CACHE`: Transformers 模型缓存
- `TORCH_HOME`: PyTorch Hub 缓存
- `SENTENCE_TRANSFORMERS_HOME`: SentenceTransformer 缓存

### 永久生效（推荐）

将以下行添加到 `~/.bashrc`：

```bash
echo 'source ~/dev_ops/YangtzeDestoryLLM/setup_storage_env.sh' >> ~/.bashrc
source ~/.bashrc
```

## 📝 配置文件更新

[`configs/cfg.yaml`](file:///home/zjx/dev_ops/YangtzeDestoryLLM/configs/cfg.yaml) 已更新：

```yaml
paths:
  # ... 原有路径配置 ...
  models_cache: "/media/data2/YangtzeDestoryLLM/models_cache"  # 模型缓存
  logs_archive: "/media/data2/YangtzeDestoryLLM/logs_archive"  # 日志归档

embedding:
  model_name: "BAAI/bge-base-zh-v1.5"
  cache_folder: "/media/data2/YangtzeDestoryLLM/models_cache"  # 使用新存储
```

## 🚀 使用示例

### 运行主流程

```bash
# 1. 激活 conda 环境
conda activate YangtzeLLM

# 2. 加载存储环境变量
source setup_storage_env.sh

# 3. 运行 P1-P5 流程
python scripts/run_cq_pipeline.py --provider zhipu --model glm-4-flash
```

### 下载新数据集

新下载的数据应存放在 `/media/data2/YangtzeDestoryLLM/data/` 或通过符号链接访问：

```bash
# 直接操作（推荐）
mkdir /media/data2/YangtzeDestoryLLM/data/new_dataset
cp /path/to/dataset/* /media/data2/YangtzeDestoryLLM/data/new_dataset/

# 或通过符号链接
mkdir data/new_dataset
cp /path/to/dataset/* data/new_dataset/
```

## 🔍 验证配置

### 检查符号链接

```bash
ls -la | grep -E "data|outputs"
# 输出应显示：
# lrwxrwxrwx  1 zjx zjx   35 ... data -> /media/data2/YangtzeDestoryLLM/data
# lrwxrwxrwx  1 zjx zjx   38 ... outputs -> /media/data2/YangtzeDestoryLLM/outputs
```

### 检查存储使用情况

```bash
df -h /media/data2
du -sh /media/data2/YangtzeDestoryLLM/*
```

### 检查环境变量

```bash
source setup_storage_env.sh
echo $HF_HOME
# 输出应为：/media/data2/YangtzeDestoryLLM/models_cache
```

## ⚠️ 注意事项

1. **备份保留**：原始 `data_backup/` 和 `outputs_backup/` 目录已保留，确认无误后可删除以节省空间

2. **模型缓存**：首次下载 BGE 模型时会自动保存到 `/media/data2/YangtzeDestoryLLM/models_cache/`

3. **日志归档**：建议定期将旧日志移动到 `logs_archive/` 目录：
   ```bash
   mv logs/*.log.* /media/data2/YangtzeDestoryLLM/logs_archive/
   ```

4. **磁盘空间监控**：虽然新存储空间充足（14T），仍建议定期检查使用情况

## 🗑️ 清理备份（可选）

确认新存储配置正常工作后，可删除备份节省空间：

```bash
# ⚠️ 请确保数据已正确迁移再执行
cd ~/dev_ops/YangtzeDestoryLLM
rm -rf data_backup outputs_backup
```

## 📊 存储空间对比

| 位置 | 之前 | 现在 |
|------|------|------|
| 根分区 `/` | 100% 满 | ~85%（释放 2.4G） |
| `/media/data2` | - | 使用 2.4G / 14T 可用 |
| 模型缓存 | 根分区 | `/media/data2` |

---

**配置完成日期**：2024-12-10  
**配置负责人**：Qoder AI Assistant
