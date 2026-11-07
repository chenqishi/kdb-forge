#!/bin/bash
# Copyright (c) 2023 qishichen, Inc. All Rights Reserved
# Authors: qishichen(chenqishi2019@gmail.com)
# Date: 2025-01-23

export LC_ALL=C
config_file=$1
source $config_file



# 保存当前目录
current_dir=$(pwd)

# 切换到脚本所在目录的上一级
cd "$(dirname "$(dirname "$0")")"
end_time=`date +"%Y%m%d%H%M%S"`
root_dir=./
export PYTHONPATH=$root_dir:$PYTHONPATH
run_record_file=$root_dir/data/query_tag/run_timing_record_query_tag.txt 

# 从记录文件读取最后一行作为start_time，如果为空则使用一个月前的时间
if [ -s "$run_record_file" ]; then
    start_time=$(tail -n 1 "$run_record_file")
else
    # 获取一个周前的时间作为start_time (兼容 macOS 和 Linux)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        start_time=`date -v-1w +"%Y%m%d%H%M%S"`
    else
        # Linux
        start_time=`date -d "1 week ago" +"%Y%m%d%H%M%S"`
    fi
fi

# 使用小时级时间做区分 (格式: YYYYMMDDHH)
end_time_hour=`date +"%Y%m%d%H"`
PYTHON=python
flag=timing_v1_${end_time_hour}
mkdir -p data/query_tag/
 #运行报告生成脚本
$PYTHON $root_dir/query_understanding_analysis/update_sql_query_tag.py batch_update_chat_history_category_from_sql  \
    --sql_config_path=config/mysql_conn_config.json \
    --start_time=$start_time \
    ---end_time=$end_time \
    --batch_size=10 \
    --need_category_mining=true &>log/update_sql_query_tag.log
# 重新获取当前时间，以囊括上面刚生成的知识

# 切换回原来的目录
echo $end_time >>$run_record_file
cd "$current_dir"
