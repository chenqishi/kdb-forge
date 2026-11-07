#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import sys
from openai import OpenAI, OpenAIError

def parse_args():
    p = argparse.ArgumentParser(
        description="从带图片的 PDF 生成分段知识（Responses API + input_file）"
    )
    p.add_argument("file", help="要上传的 PDF/文档路径")
    p.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY", ""), help="API Key（或用环境变量 OPENAI_API_KEY）")
    p.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                   help="Base URL，默认为官方 https://api.openai.com/v1")
    p.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4.1"), help="模型名，默认 gpt-4.1")
    return p.parse_args()

def main():
    args = parse_args()

    if not args.api_key:
        print("ERROR: 缺少 API Key，请用 --api-key 或设置环境变量 OPENAI_API_KEY", file=sys.stderr)
        sys.exit(2)

    if not os.path.isfile(args.file):
        print(f"ERROR: 文件不存在：{args.file}", file=sys.stderr)
        sys.exit(2)

    # 初始化客户端
    client = OpenAI(api_key=args.api_key, base_url=args.base_url)

    try:
        # 1) 上传文件：purpose 必须为 'assistants'（或 'responses'）
        with open(args.file, "rb") as fh:
            uploaded = client.files.create(file=fh, purpose="assistants")
        file_id = uploaded.id
        print(f"[info] uploaded file_id = {file_id}")

        # 2) 使用 Responses API + input_file
        prompt = (
            "请从这份文档生成分段知识：每段包含 section_title、summary、bullets，"
            "如有涉及图片，请识别要点并给出简短图片描述（image_caption）。"
            "输出语言为中文。"
        )

        resp = client.responses.create(
            model=args.model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_file", "file_id": file_id},
                    ],
                }
            ],
            # 也可设置 temperature / max_output_tokens 等
        )

        # 3) 打印结果
        # Responses API 提供便捷属性 output_text（SDK >=1.40）
        out = getattr(resp, "output_text", None)
        if out:
            print(out)
        else:
            # 兼容性兜底：直接打印对象（JSON）
            # 注意：这会比较长，如果需要可以自己解析 resp.output[0].content 等
            import json
            print(json.dumps(resp.to_dict(), ensure_ascii=False, indent=2))

    except OpenAIError as e:
        # SDK 级错误（认证、配额、参数等）
        print(f"OpenAIError: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        # 其它异常（网络、IO 等）
        print(f"Exception: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
