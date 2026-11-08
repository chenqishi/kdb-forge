#!/usr/bin/env python
# -*- coding:utf8 -*-

"""
QA 质量筛选 —— Dify workflow「qa选择过滤」的本地实现。

原 Dify 流（data/qa选择过滤.yml）是单节点：把**整份** QA 清单编号后塞进一次
LLM 调用，要求模型逐条回带标签的结果。这个设计有两个致命问题：

1. 清单一长模型就回不完，而下游 `parse_qa_quality_result` **按出现顺序重新编号**，
   模型少回一条，后面全部错位；`add_quality_info_to_qa_json_by_dify` 里
   `if i + 1 in quality_info` 取不到就把 `quality_info` 置空，进而强制降级 mid。
   实测同一批任务打标率从 99% 到 0.4% 不等，最差一次 485 条只有 2 条拿到标签。
2. 原流用的是 gemini-2.5-flash-lite，长清单上尤其容易漏条。

本地实现的改法：
  - **分块**：按 batch_size 切分，每批单独调用，块内保留全局序号（`#重复-{index}`
    引用的就是全局序号，不需要再映射）
  - **对齐校验**：每批回来的条数必须与投入条数一致，不一致先重试；仍不一致则该批
    退化为「原文无标签」输出，把损失限制在这一批，而不是整个任务错位
  - **按 client 追加规则**：prompts/quality.<client>.md

对外仍暴露 `.request_dify(paragraph)`，与 commons.dify_tools.DifyWorkFlowRequest 兼容。
"""

import logging
import os
import re
from typing import List
from typing import Optional

import kdb.mining.common.llm.config as cqe_config
import kdb.mining.common.llm.client as llm_client
from kdb.mining.common.llm.text_output import clear_think
from kdb.mining.common.llm.prompts import load_prompt

DEFAULT_BATCH_SIZE = 40

# 与 commons.qa_text_tools.parse_qa_quality_result 用的是同一族正则，
# 这里只用来数「这一块里有几条 QA」，确保投入和产出条数对得上。
_QA_BLOCK_RE = re.compile(r'问题\s*[:：]', re.DOTALL)


def count_qa_blocks(text: str) -> int:
    """统计一段文本里有多少条 QA（以 `问题:` 出现次数为准）"""
    return len(_QA_BLOCK_RE.findall(text or ''))


def split_qa_blocks(paragraph: str) -> List[str]:
    """
    把编号后的 QA 清单按 `###` 切成单条。

    上游 `commons.schema_trans.qajson_to_line_text(add_index=True)` 生成的格式是
        1.问题:xxx\n答案:yyy\n###\n2.问题:...
    """
    if not paragraph:
        return []
    blocks = [b.strip() for b in paragraph.split('###')]
    return [b for b in blocks if b and count_qa_blocks(b) > 0]


class QaQualityFilter(object):
    """本地 QA 质检过滤器，接口与原 Dify 客户端兼容。"""

    def __init__(self, client: Optional[str] = None, model: Optional[str] = None,
                 batch_size: int = DEFAULT_BATCH_SIZE, max_retries: int = 2,
                 max_tokens: int = 16000, temperature: float = 0.0,
                 timeout: int = 180, usage_out: Optional[dict] = None):
        """
        Args:
            client:     客户名，存在 prompts/quality.<client>.md 时追加其规则
            model:      模型名，默认取配置 models.quality
            batch_size: 每次送进模型的 QA 条数
            max_retries: 单批条数对不上时的重试次数
        """
        cqe_config.load_llm_config()
        self.client = client or ''
        self.model = cqe_config.get_model('quality', model)
        self.batch_size = max(1, int(batch_size))
        self.max_retries = max(1, int(max_retries))
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        self.usage_out = usage_out

        base_prompt = load_prompt('quality.default')
        augment = load_prompt(f'quality.{self.client}') if self.client else ''
        if augment:
            logging.info('QaQualityFilter: client=%s 命中增强规则 quality.%s.md', self.client, self.client)
            self.system_prompt = f'{base_prompt}\n\n{augment}'
        else:
            self.system_prompt = base_prompt

    # -- 单批处理 ---------------------------------------------------------

    def _build_query(self, batch_text: str, expect_count: int) -> str:
        return (
            f'以下是待处理的数据，共 {expect_count} 条 QA。\n'
            f'请**逐条**输出判定结果，输出条数必须同样是 {expect_count} 条，'
            f'保持输入顺序和原有序号，条与条之间用 ### 分隔，不得省略、不得合并、不得只输出有问题的条目。\n'
            f'<qa>\n{batch_text}\n</qa>'
        )

    def _process_batch(self, blocks: List[str]) -> str:
        """
        处理一批 QA，返回条数与输入一致的结果文本。

        条数始终对齐：重试仍对不上时退化为「原文无标签」，
        保证调用方按顺序解析时不会错位。
        """
        expect = len(blocks)
        batch_text = '\n###\n'.join(blocks)

        for attempt in range(self.max_retries):
            content, detail = llm_client.request_llm(
                model_name=self.model,
                query=self._build_query(batch_text, expect),
                system_message=self.system_prompt,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                timeout=self.timeout,
                usage_out=self.usage_out,
            )
            content = clear_think(content)
            if not content:
                logging.warning('QaQualityFilter: 第 %d 次返回为空, expect=%d, detail=%s',
                                attempt + 1, expect, detail[:200])
                continue

            got = count_qa_blocks(content)
            if got == expect:
                return content
            logging.warning('QaQualityFilter: 第 %d 次条数不符 expect=%d got=%d，重试',
                            attempt + 1, expect, got)

        logging.error('QaQualityFilter: 本批对齐失败，退化为无标签输出以保证顺序 (expect=%d)', expect)
        return '\n###\n'.join(blocks)

    # -- 对外接口 ---------------------------------------------------------

    def request_dify(self, paragraph: str, other_inputs: Optional[dict] = None) -> Optional[str]:
        """
        Args:
            paragraph: `qajson_to_line_text(qa_list, add_index=True)` 生成的编号 QA 清单

        Returns:
            与输入条数一致、可被 parse_qa_quality_result 顺序解析的结果文本；
            输入为空时返回 None
        """
        blocks = split_qa_blocks(paragraph)
        if not blocks:
            logging.warning('QaQualityFilter: 输入解析不出 QA, len=%d', len(paragraph or ''))
            return None

        total = len(blocks)
        outputs: List[str] = []
        for start in range(0, total, self.batch_size):
            batch = blocks[start:start + self.batch_size]
            logging.info('QaQualityFilter: 处理第 %d-%d 条 / 共 %d 条',
                         start + 1, start + len(batch), total)
            outputs.append(self._process_batch(batch))

        result = '\n###\n'.join(outputs)
        final_count = count_qa_blocks(result)
        if final_count != total:
            # 分块本身保证了对齐，走到这里说明某批的原文里 `问题:` 数量异常，记日志便于排查
            logging.error('QaQualityFilter: 总条数仍不一致 expect=%d got=%d', total, final_count)
        return result


def build_quality_filter(client: Optional[str] = None, **kwargs) -> QaQualityFilter:
    """工厂函数"""
    return QaQualityFilter(client=client, **kwargs)
