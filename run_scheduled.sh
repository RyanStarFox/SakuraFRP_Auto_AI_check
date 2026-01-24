#!/bin/bash

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

# 如果不存在当天的随机时间文件，则生成一个
if [ ! -f "$RANDOM_TIME_FILE" ]; then
    echo "[INFO] 生成当天的随机执行时间..."
    
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
fi

# 读取当天的随机时间
RANDOM_TIME=$(cat "$RANDOM_TIME_FILE" | tr -d '\n\r ')

# 解析随机时间（HH:MM:SS格式）
IFS=':' read -r RANDOM_HOUR RANDOM_MIN RANDOM_SEC <<< "$RANDOM_TIME"

# 获取当前时间
CURRENT_HOUR=$(date +%H)
CURRENT_MIN=$(date +%M)

# 检查是否已经执行过（避免重复执行）
LOCK_FILE=".executed_${CURRENT_DATE}.lock"
if [ -f "$LOCK_FILE" ]; then
    LOCK_TIME=$(cat "$LOCK_FILE" | tr -d '\n\r ')
    if [ "$LOCK_TIME" = "${CURRENT_HOUR}:${CURRENT_MIN}" ]; then
        # 已经在当前分钟执行过，退出
        exit 0
    fi
fi

# 比较当前时间是否匹配随机时间（精确到分钟）
# 由于cron每分钟执行一次（在第0秒执行），我们检查当前分钟是否匹配随机时间的分钟
# 随机秒数用于增加随机性，但实际执行会在匹配分钟的第0秒
if [ "$CURRENT_HOUR" = "$RANDOM_HOUR" ] && [ "$CURRENT_MIN" = "$RANDOM_MIN" ]; then
    # 记录执行时间
    echo "${CURRENT_HOUR}:${CURRENT_MIN}" > "$LOCK_FILE"
    CURRENT_TIME_FULL=$(date +%H:%M:%S)
    echo "[INFO] 当前时间 $CURRENT_TIME_FULL 匹配随机时间 $RANDOM_TIME，开始执行签到脚本..."
    
    # 执行Python脚本
    # 优先使用uv虚拟环境，如果存在
    if [ -d ".venv" ] && [ -f ".venv/bin/python" ]; then
        echo "[INFO] 使用uv虚拟环境执行脚本"
        .venv/bin/python main.py --both
    elif command -v uv &> /dev/null; then
        echo "[INFO] 使用uv run执行脚本"
        uv run main.py --both
    elif command -v python3 &> /dev/null; then
        echo "[INFO] 使用python3执行脚本"
        python3 main.py --both
    elif command -v python &> /dev/null; then
        echo "[INFO] 使用python执行脚本"
        python main.py --both
    else
        echo "[ERROR] 未找到Python解释器"
        exit 1
    fi
    
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        echo "[INFO] 签到脚本执行完成"
    else
        echo "[ERROR] 签到脚本执行失败，退出码: $EXIT_CODE"
    fi
    exit $EXIT_CODE
else
    # 时间不匹配，静默退出（不输出任何信息，避免cron日志过多）
    exit 0
fi
