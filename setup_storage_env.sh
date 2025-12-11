#!/bin/bash
# 项目存储环境变量配置
# 
# 用途：配置 HuggingFace/Torch 等库使用新存储空间
# 使用方式：source setup_storage_env.sh

# HuggingFace 模型缓存路径
export HF_HOME="/media/data2/YangtzeDestoryLLM/models_cache"
export TRANSFORMERS_CACHE="/media/data2/YangtzeDestoryLLM/models_cache/transformers"
export HF_DATASETS_CACHE="/media/data2/YangtzeDestoryLLM/models_cache/datasets"

# Torch Hub 缓存路径
export TORCH_HOME="/media/data2/YangtzeDestoryLLM/models_cache/torch"

# Sentence Transformers 缓存路径
export SENTENCE_TRANSFORMERS_HOME="/media/data2/YangtzeDestoryLLM/models_cache/sentence_transformers"

# 创建必要的目录
mkdir -p "$HF_HOME"
mkdir -p "$TRANSFORMERS_CACHE"
mkdir -p "$HF_DATASETS_CACHE"
mkdir -p "$TORCH_HOME"
mkdir -p "$SENTENCE_TRANSFORMERS_HOME"

echo "✅ 存储环境变量已配置："
echo "   HF_HOME: $HF_HOME"
echo "   TRANSFORMERS_CACHE: $TRANSFORMERS_CACHE"
echo "   TORCH_HOME: $TORCH_HOME"
echo ""
echo "💡 提示：建议将以下命令添加到 ~/.bashrc 以永久生效："
echo "   echo 'source ~/dev_ops/YangtzeDestoryLLM/setup_storage_env.sh' >> ~/.bashrc"
