#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2023 Tencent.com, Inc. All Rights Reserved
# Authors: qishichen(qishichen@tencent.com)
# Date: 2024-11-01

import os
import sys
import subprocess
import shlex

from kdb.shared.config.paths import PROJECT_ROOT
from kdb.shared.config.paths import subprocess_env

def main():
    # 获取命令行参数
    need_report_file = sys.argv[1]
    es_config_file = sys.argv[2]
    data_dir = sys.argv[3]
    start_time = sys.argv[4]
    end_time = sys.argv[5]
    flag = sys.argv[6]

    # 设置环境变量
    audit_script = PROJECT_ROOT / 'scripts' / 'operations' / 'export_audit_data.sh'
    child_env = subprocess_env()

    # 读取需要处理的平台和URL
    with open(need_report_file, 'r', encoding='utf-8') as f:
        for line in f:
            platform, receiver, send_url = line.strip().split('\t')
            
            # 执行 gen_audit_data.sh
            audit_cmd = f"sh -x {shlex.quote(str(audit_script))} {platform} {es_config_file} -1 {data_dir} {flag} high chat_auto"
            with open(f'log/gen_audit_{flag}.log', 'w') as f:
                subprocess.run(audit_cmd, shell=True, stdout=f, stderr=f, env=child_env)
            
            # 执行报告生成命令
            report_cmd = [
                sys.executable,
                '-m',
                'kdb.mining.chat.reports.knowledge',
                "gen_chatknowledge_report",
                f"--json_data_file={data_dir}/audit_data_{flag}.txt",
                f"--excel_file_path={data_dir}/audit_data_excel_{platform}_{flag}.xlsx",
                f"--start_time={start_time}",
                f"--end_time={end_time}",
                f"--receiver=\"{receiver}\"",
                f"--send_url={send_url}"
            ]
            with open('log/chatknowledge_report.log', 'w') as f:
                subprocess.run(report_cmd, stdout=f, stderr=f, env=child_env)

if __name__ == "__main__":
    main()
