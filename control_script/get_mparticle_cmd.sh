#!/bin/bash
# Copyright (c) 2024 chenqishi2019@gmail.com, Inc. All Rights Reserved
# Authors: qishichen(chenqishi2019@gmail.com)
# Date: 2025-02-14
export LC_ALL=C

#公众号的获取就是手工curl操作，没做python那么复杂
curl -X POST "https://api.weixin.qq.com/cgi-bin/freepublish/batchget?access_token=${ACCESS_TOKEN}" -H "Content-Type: application/json" -d '{
    "offset":0,
    "count":20,
    "no_content":1
}'  >data/letian_article_tmp.txt

curl -X POST "https://api.weixin.qq.com/cgi-bin/material/batchget_material?access_token=${ACCESS_TOKEN}" -H "Content-Type: application/json" -d '{
        "type":"news",
    "offset":0,
    "count":10
}' >>data/letian_article_tmp2.txt
