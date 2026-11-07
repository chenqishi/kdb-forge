#!/bin/bash
# Copyright (c) 2023 qishichen, Inc. All Rights Reserved
# Authors: qishichen(chenqishi2019@gmail.com)
# Date: 2025-01-23

export LC_ALL=C

# 检查参数数量
if [ $# -lt 4 ]; then
    echo "用法: $0 <config_file> <start_time> <end_time> <batch_size> [white_client_set]"
    echo "参数说明:"
    echo "  config_file: 配置文件路径"
    echo "  start_time: 开始时间 (格式: YYYYMMDD)"
    echo "  end_time: 结束时间 (格式: YYYYMMDD)"
    echo "  batch_size: 并行进程数量"
    echo "  white_client_set: 可选，客户端白名单"
    echo "示例: $0 config/mysql_conn_config.json 20250101 20250131 3"
    exit 1
fi

config_file=$1
start_time_param=$2
end_time_param=$3
batch_size=$4
white_client_set=$5

# 验证时间格式
if ! [[ $start_time_param =~ ^[0-9]{8}$ ]]; then
    echo "错误: start_time格式不正确，应为YYYYMMDD格式"
    exit 1
fi

if ! [[ $end_time_param =~ ^[0-9]{8}$ ]]; then
    echo "错误: end_time格式不正确，应为YYYYMMDD格式"
    exit 1
fi

# 验证时间范围
if [ $start_time_param -gt $end_time_param ]; then
    echo "错误: start_time不能大于end_time"
    exit 1
fi

# 验证batch_size
if ! [[ $batch_size =~ ^[0-9]+$ ]] || [ $batch_size -lt 1 ]; then
    echo "错误: batch_size必须是大于0的整数"
    exit 1
fi

source $config_file

# 保存当前目录
current_dir=$(pwd)

# 切换到脚本所在目录的上一级
cd "$(dirname "$(dirname "$0")")"
root_dir=./
export PYTHONPATH=$root_dir:$PYTHONPATH

PYTHON=python
mkdir -p data/query_tag/
mkdir -p log/

# 将日期转换为时间戳进行比较
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    start_timestamp=$(date -j -f "%Y%m%d" "$start_time_param" +%s)
    end_timestamp=$(date -j -f "%Y%m%d" "$end_time_param" +%s)
else
    # Linux
    start_timestamp=$(date -d "$start_time_param" +%s)
    end_timestamp=$(date -d "$end_time_param" +%s)
fi

# 生成所有需要处理的日期列表（从最新到最远）
dates_to_process=()
current_timestamp=$end_timestamp

while [ $current_timestamp -ge $start_timestamp ]; do
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        current_date=$(date -r $current_timestamp +"%Y%m%d")
    else
        # Linux
        current_date=$(date -d "@$current_timestamp" +"%Y%m%d")
    fi
    dates_to_process+=($current_date)
    current_timestamp=$((current_timestamp - 86400))
done

echo "开始处理时间范围: $start_time_param 到 $end_time_param"
echo "处理顺序: 从最新时间到最远时间"
echo "并行进程数: $batch_size"
echo "总共需要处理 ${#dates_to_process[@]} 天"

# 进程管理函数
process_dates() {
    local date=$1
    local day_start_time="${date}000000"
    local day_end_time="${date}235959"
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始处理日期: $date (从 $day_start_time 到 $day_end_time)"
    
    # 构建命令
    local cmd="$PYTHON $root_dir/query_understanding_analysis/update_sql_query_tag.py batch_update_chat_history_category_from_sql"
    cmd="$cmd --sql_config_path=config/mysql_conn_config.json"
    cmd="$cmd --start_time=$day_start_time"
    cmd="$cmd --end_time=$day_end_time"
    cmd="$cmd --batch_size=1"
    cmd="$cmd --need_cover=true"
    if [ -n "$white_client_set" ]; then
        cmd="$cmd --client_white_set=$white_client_set"
    fi
    cmd="$cmd --need_category_mining=false"
    cmd="$cmd &>log/update_sql_query_tag_${date}.log"
    
    # 执行命令
    eval $cmd
    local exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 日期 $date 处理成功"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 日期 $date 处理失败，请检查日志: log/update_sql_query_tag_${date}.log"
    fi
    
    return $exit_code
}

# 并行处理逻辑
declare -a pids=()
declare -a current_dates=()
date_index=0
total_dates=${#dates_to_process[@]}
completed_count=0

echo "开始并行处理..."

# 启动初始批次进程
for ((i=0; i<batch_size && i<total_dates; i++)); do
    date=${dates_to_process[$date_index]}
    process_dates $date &
    pid=$!
    pids+=($pid)
    current_dates+=($date)
    echo "启动进程 $pid 处理日期 $date"
    ((date_index++))
done

# 监控进程并启动新进程
while [ $completed_count -lt $total_dates ]; do
    for i in "${!pids[@]}"; do
        if ! kill -0 ${pids[$i]} 2>/dev/null; then
            # 进程已结束
            wait ${pids[$i]}
            exit_code=$?
            completed_date=${current_dates[$i]}
            ((completed_count++))
            
            if [ $exit_code -eq 0 ]; then
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] 进程 $completed_count/$total_dates 完成: $completed_date"
            else
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] 进程 $completed_count/$total_dates 失败: $completed_date"
            fi
            
            # 如果有更多日期需要处理，启动新进程
            if [ $date_index -lt $total_dates ]; then
                new_date=${dates_to_process[$date_index]}
                process_dates $new_date &
                new_pid=$!
                pids[$i]=$new_pid
                current_dates[$i]=$new_date
                echo "启动新进程 $new_pid 处理日期 $new_date"
                ((date_index++))
            else
                # 移除已完成的进程
                unset pids[$i]
                unset current_dates[$i]
            fi
        fi
    done
    
    # 重新索引数组
    pids=("${pids[@]}")
    current_dates=("${current_dates[@]}")
    
    # 短暂休眠避免过度占用CPU
    sleep 1
done

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 所有日期处理完成"

# 切换回原来的目录
cd "$current_dir"
