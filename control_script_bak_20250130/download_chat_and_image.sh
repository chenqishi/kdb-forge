#!/bin/bash
# Copyright (c) 2023 qishichen, Inc. All Rights Reserved
# Authors: qishichen(chenqishi2019@gmail.com)
# Date: 2025-01-04
export LC_ALL=C

batch_data_file=$1 #机器人\t平台\t数据地址
data_dir=$2
log_dir=$3
flag=$4

root_dir=./
export PYTHONPATH=$root_dir:$PYTHONPATH
PYTHON=python

$PYTHON $root_dir/data_control_tools/remote_machine_tools.py run_batch_download_files \
    --batch_file_path=$batch_data_file \
    --output_file_path=$data_dir/download_file_batch_${flag}.txt \
    --save_data_dir=$data_dir \
    --remote_field_num=2 \
    --username=root \
    --password="$(cat "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)/private/runtime_config/shell/a7d2716a8326bf65b673.value")" \
    --port=22


python $root_dir/data_control_tools/remote_machine_tools.py run_batch_process_message \
    --input_file_path=$data_dir/download_file_batch_${flag}.txt \
    --output_file_path=$data_dir/download_file_batch_${flag}_add_image.txt \
    --save_image_dir=$data_dir/image_down \
    --remote_field_num=2 \
    --local_field_num=3 \
    --username=root \
    --password="$(cat "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)/private/runtime_config/shell/a7d2716a8326bf65b673.value")" \
    --port=22
 
 