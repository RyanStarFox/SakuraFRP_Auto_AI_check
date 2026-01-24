#!/bin/bash

# 执行脚本 - 检查时间并执行签到
# 在时间窗口内每分钟执行一次，检查是否匹配随机时间

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

# 获取当前日期（YYYY-MM-DD格式）
CURRENT_DATE=$(date +%Y-%m-%d)

# 随机时间文件路径
RANDOM_TIME_FILE="random_time_${CURRENT_DATE}.txt"

# 检查随机时间文件是否存在
if [ ! -f "$RANDOM_TIME_FILE" ]; then
    # 如果随机时间文件不存在，静默退出（可能抽签脚本还未执行）
    exit 0
fi

# 读取当天的随机时间
RANDOM_TIME=$(cat "$RANDOM_TIME_FILE" | tr -d '\n\r ')

# 解析随机时间（HH:MM:SS格式）
IFS=':' read -r RANDOM_HOUR RANDOM_MIN RANDOM_SEC <<< "$RANDOM_TIME"

# 获取当前时间
CURRENT_HOUR=$(date +%H)
CURRENT_MIN=$(date +%M)
CURRENT_SEC=$(date +%S)

# 检查是否已经执行过（避免重复执行）
LOCK_FILE=".executed_${CURRENT_DATE}.lock"
if [ -f "$LOCK_FILE" ]; then
    # 如果锁文件存在，说明今天已经执行过了
    exit 0
fi

# 检查当前时间是否匹配随机时间（精确到分钟）
if [ "$CURRENT_HOUR" = "$RANDOM_HOUR" ] && [ "$CURRENT_MIN" = "$RANDOM_MIN" ]; then
    # 分钟匹配，现在检查秒数
    # 如果当前秒数小于目标秒数，等待到目标秒数
    if [ "$CURRENT_SEC" -lt "$RANDOM_SEC" ]; then
        # 计算需要等待的秒数
        WAIT_SECONDS=$((RANDOM_SEC - CURRENT_SEC))
        echo "[INFO] 当前时间 $(date +%H:%M:%S)，等待 ${WAIT_SECONDS} 秒到目标时间 $RANDOM_TIME..."
        sleep $WAIT_SECONDS
    elif [ "$CURRENT_SEC" -gt "$RANDOM_SEC" ]; then
        # 如果已经过了目标秒数（可能cron执行延迟），直接执行
        echo "[INFO] 当前时间 $(date +%H:%M:%S)，已超过目标秒数，立即执行..."
    fi
    
    # 再次检查锁文件（防止并发执行）
    if [ -f "$LOCK_FILE" ]; then
        exit 0
    fi
    
    # 创建锁文件
    echo "$(date +%H:%M:%S)" > "$LOCK_FILE"
    
    CURRENT_TIME_FULL=$(date +%H:%M:%S)
    echo "[INFO] 当前时间 $CURRENT_TIME_FULL，匹配随机时间 $RANDOM_TIME，开始执行签到脚本..."
    
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
        rm -f "$LOCK_FILE"
        exit 1
    fi
    
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        echo "[INFO] 签到脚本执行完成"
    else
        echo "[ERROR] 签到脚本执行失败，退出码: $EXIT_CODE"
        # 执行失败时删除锁文件，允许重试
        rm -f "$LOCK_FILE"
    fi
    exit $EXIT_CODE
else
    # 时间不匹配，静默退出（不输出任何信息，避免cron日志过多）
    exit 0
fi
