#!/bin/bash
# 上 HPC 前最终检查脚本

echo "================================================================================"
echo "上 HPC (LSF) 前最终检查"
echo "================================================================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=0
FAIL=0

# 检查 1: 核心文件存在
echo "检查 1: 核心文件存在"
echo "--------------------------------------------------------------------------------"

files=(
    "src/simulation/policies.py"
    "src/simulation/rolling_horizon_integrated.py"
    "src/simulation/risk_gate.py"
    "models/risk_model.joblib"
    "data/processed/multiday_benchmark_herlev.json"
    "scripts/quick_acceptance_test.py"
)

for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $file"
        ((PASS++))
    else
        echo -e "${RED}✗${NC} $file (缺失)"
        ((FAIL++))
    fi
done

echo ""

# 检查 2: Python 依赖
echo "检查 2: Python 依赖"
echo "--------------------------------------------------------------------------------"

python3 -c "import sklearn, numpy, pandas, joblib" 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} 所有依赖已安装"
    ((PASS++))
else
    echo -e "${RED}✗${NC} 缺少依赖，请运行: pip install -r requirements.txt"
    ((FAIL++))
fi

echo ""

# 检查 3: 运行核验脚本
echo "检查 3: 运行核验脚本"
echo "--------------------------------------------------------------------------------"

python3 scripts/pre_hpc_validation.py > /tmp/validation_output.txt 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} 核验脚本通过"
    ((PASS++))
else
    echo -e "${RED}✗${NC} 核验脚本失败，查看详情: /tmp/validation_output.txt"
    ((FAIL++))
fi

echo ""

# 检查 4: 验收测试结果存在
echo "检查 4: 验收测试结果"
echo "--------------------------------------------------------------------------------"

if [ -f "data/results/ACCEPTANCE_TEST/BAU/ProactiveRisk/daily_stats.csv" ] && \
   [ -f "data/results/ACCEPTANCE_TEST/Crunch/ProactiveRisk/daily_stats.csv" ]; then
    echo -e "${GREEN}✓${NC} 验收测试结果存在"
    ((PASS++))
else
    echo -e "${YELLOW}⚠${NC}  验收测试结果不存在，建议运行: python3 scripts/quick_acceptance_test.py"
fi

echo ""

# 检查 5: LSF 任务脚本存在
echo "检查 5: LSF 任务脚本"
echo "--------------------------------------------------------------------------------"

if [ -d "jobs" ]; then
    lsf_count=$(find jobs -name "*.lsf" 2>/dev/null | wc -l)
    if [ $lsf_count -gt 0 ]; then
        echo -e "${GREEN}✓${NC} 找到 $lsf_count 个 LSF 脚本"
        ((PASS++))
    else
        echo -e "${YELLOW}⚠${NC}  未找到 .lsf 文件，可能需要运行: python3 scripts/generate_hpc_jobs.py"
    fi
else
    echo -e "${YELLOW}⚠${NC}  jobs/ 目录不存在"
fi

echo ""

# 总结
echo "================================================================================"
echo "检查总结"
echo "================================================================================"
echo -e "通过: ${GREEN}$PASS${NC}"
echo -e "失败: ${RED}$FAIL${NC}"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}✅ 所有检查通过，可以提交到 HPC (LSF)${NC}"
    echo ""
    echo "提交命令:"
    echo "  bash jobs/submit_all.sh"
    echo "  或手动: bsub < jobs/your_job.lsf"
    echo ""
    echo "监控命令:"
    echo "  bjobs                    # 查看任务状态"
    echo "  bjobs -l <job_id>        # 查看详细信息"
    echo "  bpeek <job_id>           # 查看实时输出"
    echo ""
    exit 0
else
    echo -e "${RED}❌ 有 $FAIL 个检查失败，请修复后再提交${NC}"
    echo ""
    exit 1
fi
