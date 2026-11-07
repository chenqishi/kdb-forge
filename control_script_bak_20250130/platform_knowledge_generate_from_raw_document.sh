#!/bin/bash
# Copyright (c) 2023 Tencent.com, Inc. All Rights Reserved
# Authors: qishichen(qishichen@tencent.com)
# Date: 2024-11-01
export LC_ALL=C
#root_dir=$(cd $(dirname $0); pwd)
root_dir=/Users/chenqishi/stone_fish/knowledge_database_builder
export PYTHONPATH=$root_dir:$PYTHONPATH

platform_raw_dat_dir_map_file=$1
data_dir=$2
log_dir=$3
flag=$4
api_key=$5
dataset_map_file=$6

PYTHON=python

$PYTHON $root_dir/knowledge_clear_tool/wordtotext.py batch_dir_trans $platform_raw_dat_dir_map_file 1>$data_dir/all_trans_to_text_${flag}.txt 2>$log_dir/all_trans_to_text_${flag}.log
# translated 当前没用到，采用源文件已原地修改的方法
$PYTHON $root_dir/knowledge_clear_tool/knowledge_translate_by_dify.py run_batch_translate_pdf_json_content $data_dir/all_trans_to_text_${flag}.txt 1>$data_dir/all_trans_to_text_${flag}_translated.txt 2>$log_dir/all_trans_to_text_${flag}_translated.log
# clear to qa
$PYTHON $root_dir/knowledge_clear_tool/knowledge_clear_by_dify_model_longcontent.py run_batch_clear_pdf_json_content  $data_dir/all_trans_to_text_${flag}.txt  ${flag} 1 1>$data_dir/all_clear_qa_file.txt 2>$log_dir/all_clear_qa_file_${flag}.log
$PYTHON $root_dir/quality_tools/qa_quality_tools.py run_batch_re_clear_qa_info --input_file=${data_dir}/all_clear_qa_file.txt --output_file=${data_dir}/all_reclear_qa_file.txt --process_field_num=-1 &>${log_dir}/run_batch_re_clear_qa_info_${flag}.log

$PYTHON $root_dir/knowledge_clear_tool/tools/schema_trans.py batch_split_json_quality_to_excel \
    --batch_file=$data_dir/all_reclear_qa_file.txt \
    --from_file_name_field_num=1 \
    --platform_field_num=0 \
    --high_quality_excel_file=$data_dir/high_quality_${flag}.xlsx \
    --mid_quality_excel_file=$data_dir/mid_quality_${flag}.xlsx \
    --low_quality_excel_file=$data_dir/low_quality_${flag}.xlsx \
    --field_num=7 2>$log_dir/batch_split_json_quality_to_excel_${flag}.log
##$PYTHON $root_dir/knowledge_clear_tool/excel_clear.py process_audit_excel $data_dir/high_quality_${flag}.xlsx 1>$data_dir/high_quality_for_qa_${flag}.txt 2>$log_dir/hight_quality_for_qa_${flag}.log
##awk -F"\t" '{print $2}' $data_dir/high_quality_for_qa_${flag}.txt >$data_dir/high_quality_for_qa_onlyjson_${flag}.txt
$PYTHON $root_dir/knowledge_clear_tool/tools/schema_trans.py batch_select_high_quality_qa_to_json \
    --batch_file=$data_dir/all_reclear_qa_file.txt \
    --platform_field_num=0 \
    --field_num=7 1>$data_dir/high_quality_for_qa_onlyjson_${flag}.txt 2>$log_dir/batch_select_high_quality_qa_to_json_${flag}.log
$PYTHON $root_dir/knowledge_search_database/fastgpt_dataset_build.py batch_add_qa_dataset $data_dir/high_quality_for_qa_onlyjson_${flag}.txt ${dataset_map_file} ${api_key} 0 &>$log_dir/batch_add_segment_qa_dataset_${flag}.log


# segment dataset
$PYTHON $root_dir/knowledge_generate/knowlege_segment_builder_by_dify.py run_batch_get_segment_knowledge $data_dir/all_trans_to_text_${flag}.txt $flag 1 0 1 1>$data_dir/segment_getindex_${flag}.txt  2>$log_dir/segment_getindex_model_${flag}.log
$PYTHON $root_dir/knowledge_search_database/fastgpt_dataset_build.py batch_add_segment_dataset $data_dir/segment_getindex_${flag}.txt  $dataset_map_file $api_key  &>$log_dir/build_segment_dataset_${flag}.log


