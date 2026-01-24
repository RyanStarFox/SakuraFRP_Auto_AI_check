#!/bin/bash

# 抽签脚本 - 生成当天的随机执行时间
# 在时间窗口开始前执行（例如：如果签到时间是8:30，则在7:30执行此脚本）

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 加载.env文件
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
else
    echo "[ERROR] .env文件不存在，请先创建.env文件"
    exit 1
fi

# 检查SCHEDULE_TIME配置
if [ -z "$SCHEDULE_TIME" ]; then
    echo "[ERROR] SCHEDULE_TIME未配置，请在.env文件中设置"
    exit 1
fi

# 解析SCHEDULE_TIME（格式：HH:MM）
IFS=':' read -r SCHEDULE_HOUR SCHEDULE_MINUTE <<< "$SCHEDULE_TIME"

# 获取当前日期（YYYY-MM-DD格式）
CURRENT_DATE=$(date +%Y-%m-%d)

# 随机时间文件路径
RANDOM_TIME_FILE="random_time_${CURRENT_DATE}.txt"

# 如果已存在当天的随机时间文件，先删除（重新抽签）
if [ -f "$RANDOM_TIME_FILE" ]; then
    echo "[INFO] 发现已存在的随机时间文件，将重新生成..."
    rm "$RANDOM_TIME_FILE"
fi

# 生成随机执行时间
echo "[INFO] 正在生成当天的随机执行时间..."

# 计算时间范围（±30分钟）
# 将时间转换为分钟数
SCHEDULE_TOTAL_MINUTES=$((SCHEDULE_HOUR * 60 + SCHEDULE_MINUTE))
START_MINUTES=$((SCHEDULE_TOTAL_MINUTES - 30))
END_MINUTES=$((SCHEDULE_TOTAL_MINUTES + 30))

# 确保时间范围在0-1439之间（一天的总分钟数）
if [ $START_MINUTES -lt 0 ]; then
    START_MINUTES=0
fi
if [ $END_MINUTES -ge 1440 ]; then
    END_MINUTES=1439
fi

# 随机选择分钟数（在范围内）
RANDOM_MINUTES=$((START_MINUTES + RANDOM % (END_MINUTES - START_MINUTES + 1)))

# 随机选择秒数（0-59）
RANDOM_SECONDS=$((RANDOM % 60))

# 转换回HH:MM:SS格式
RANDOM_HOUR=$((RANDOM_MINUTES / 60))
RANDOM_MIN=$((RANDOM_MINUTES % 60))

# 格式化时间（确保两位数）
RANDOM_TIME=$(printf "%02d:%02d:%02d" $RANDOM_HOUR $RANDOM_MIN $RANDOM_SECONDS)

# 保存到文件
echo "$RANDOM_TIME" > "$RANDOM_TIME_FILE"
echo "[INFO] 当天的随机执行时间已生成: $RANDOM_TIME"
echo "[INFO] 签到将在 $RANDOM_TIME 执行"
