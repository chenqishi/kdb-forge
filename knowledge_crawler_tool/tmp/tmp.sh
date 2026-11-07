#!/bin/bash
# Copyright (c) 2023 Tencent.com, Inc. All Rights Reserved
# Authors: qishichen(qishichen@tencent.com)
# Date: 2024-10-20
export LC_ALL=C
python -u  web_crawl/web_deep_crawler.py run_all --base_url="https://help.octopia.com/s/?language=en_US" --output_dir="data/crawled_data" 
python  -u web_crawl/web_deep_crawler.py run_article --base_url="https://help.octopia.com/s/?language=en_US" --output_dir="data/crawled_data"
