#!/bin/bash
# 存储配置验证脚本

echo "========================================="
echo "  存储配置验证"
echo "========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. 检查符号链接
echo "1️⃣  检查符号链接..."
if [ -L "data" ] && [ -L "outputs" ]; then
    echo -e "  ${GREEN}✓${NC} data -> $(readlink data)"
    echo -e "  ${GREEN}✓${NC} outputs -> $(readlink outputs)"
else
    echo -e "  ${RED}✗${NC} 符号链接未正确创建"
    exit 1
fi
echo ""

# 2. 检查新存储目录
echo "2️⃣  检查新存储目录..."
if [ -d "/media/data2/YangtzeDestoryLLM" ]; then
    echo -e "  ${GREEN}✓${NC} /media/data2/YangtzeDestoryLLM 存在"
    du -sh /media/data2/YangtzeDestoryLLM/* 2>/dev/null | while read size dir; do
        echo "      $size  $(basename $dir)"
    done
else
    echo -e "  ${RED}✗${NC} 新存储目录不存在"
    exit 1
fi
echo ""

# 3. 检查数据完整性
echo "3️⃣  检查数据完整性..."
data_count=$(find data/ -type f 2>/dev/null | wc -l)
output_count=$(find outputs/ -type f 2>/dev/null | wc -l)
echo -e "  ${GREEN}✓${NC} data/ 包含 $data_count 个文件"
echo -e "  ${GREEN}✓${NC} outputs/ 包含 $output_count 个文件"
echo ""

# 4. 检查环境变量
echo "4️⃣  检查环境变量..."
if [ -f "setup_storage_env.sh" ]; then
    source setup_storage_env.sh > /dev/null 2>&1
    if [ -n "$HF_HOME" ]; then
        echo -e "  ${GREEN}✓${NC} HF_HOME=${HF_HOME}"
    else
        echo -e "  ${YELLOW}⚠${NC} 环境变量未设置，请运行: source setup_storage_env.sh"
    fi
else
    echo -e "  ${RED}✗${NC} setup_storage_env.sh 不存在"
fi
echo ""

# 5. 检查可用空间
echo "5️⃣  检查可用空间..."
df -h /media/data2 | tail -1 | awk '{print "  可用空间: "$4" / "$2" (已用 "$5")"}'
echo ""

echo "========================================="
echo -e "${GREEN}✅ 存储配置验证完成！${NC}"
echo "========================================="
echo ""
echo "📖 详细配置说明请参阅: STORAGE_CONFIG.md"
