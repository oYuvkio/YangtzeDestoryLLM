#!/bin/bash
# -*- coding: utf-8 -*-
# 快速验证向量去重功能

set -e  # 遇到错误立即退出

echo "========================================"
echo "  向量去重功能快速验证"
echo "========================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 检查环境
echo -e "${YELLOW}[1/5]${NC} 检查 Python 环境..."
if ! command -v conda &> /dev/null; then
    echo -e "${RED}✗ conda 未安装${NC}"
    exit 1
fi

# 激活环境
echo -e "${YELLOW}[2/5]${NC} 激活 YangtzeLLM 环境..."
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate YangtzeLLM || {
    echo -e "${RED}✗ 无法激活 YangtzeLLM 环境${NC}"
    exit 1
}
echo -e "${GREEN}✓ 环境已激活${NC}"

# 检查配置
echo -e "${YELLOW}[3/5]${NC} 验证配置文件..."
python3 scripts/verify_config.py

if [ $? -ne 0 ]; then
    echo -e "${RED}✗ 配置检查失败${NC}"
    exit 1
fi
echo -e "${GREEN}✓ 配置检查通过${NC}"

# 测试去重功能
echo -e "${YELLOW}[4/5]${NC} 测试向量去重功能（不调用 LLM）..."
python scripts/verify_full_pipeline.py --test-dedup-only

if [ $? -ne 0 ]; then
    echo -e "${RED}✗ 去重测试失败${NC}"
    exit 1
fi
echo -e "${GREEN}✓ 去重测试通过${NC}"

# 代码结构验证
echo -e "${YELLOW}[5/5]${NC} 验证代码结构..."
python scripts/verify_full_pipeline.py --skip-llm --skip-config-check

if [ $? -ne 0 ]; then
    echo -e "${RED}✗ 代码结构验证失败${NC}"
    exit 1
fi
echo -e "${GREEN}✓ 代码结构验证通过${NC}"

echo ""
echo "========================================"
echo -e "${GREEN}✓ 所有检查通过！${NC}"
echo "========================================"
echo ""
echo "📋 下一步操作建议："
echo "  1. 运行完整流程测试（会调用 LLM）："
echo "     python scripts/verify_full_pipeline.py"
echo ""
echo "  2. 运行对比实验："
echo "     python experiments/exp_dedup_comparison.py"
echo ""
echo "  3. 运行主流程："
echo "     python scripts/run_cq_pipeline.py --provider zhipu --model glm-4.5-flash"
echo ""
