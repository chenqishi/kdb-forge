#!/bin/bash
# Copyright (c) 2023 qishichen, Inc. All Rights Reserved
# Authors: qishichen(chenqishi2019@gmail.com)
# Date: 2025-01-23

export LC_ALL=C
config_file=$1
source $config_file



# 保存当前目录
current_dir=$(pwd)
CONFIG_PATH=config/config_es_engine.json
# 切换到脚本所在目录的上一级
cd "$(dirname "$(dirname "$0")")"
root_dir=./
export PYTHONPATH=$root_dir:$PYTHONPATH
# 获取一小时前的时间作为end_time (格式: YYYYMMDDHHmmss)
#end_time=`date -v-1H +"%Y%m%d%H%M%S"`
end_time=`date -d "1 hour ago" +"%Y%m%d%H%M%S"`
PYTHON=python
$PYTHON control_script/timing_auto_audit_kg.py \
    --config ${CONFIG_PATH} \
    --index "all" \
    --from-type-norm "document,html" \
    --hours 2400 1>log/auto_audit_all.log.${end_time} 2>1 &
