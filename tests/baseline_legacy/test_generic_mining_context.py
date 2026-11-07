"""通用 document_qa_segment_mining 上下文增强改造的离线单元测试。

覆盖（均不依赖 DB / 网络 / 远程 LLM）：
- 通用质量后处理：栏目式泛标题补全、悬空指代 needs_review、boilerplate 拒绝。
- 业务上下文构建：enable_context_enrichment=false 时不增强、不查 chat、不联网。
- chat query 清洗规则 + 无配置时降级为空。
- web 业务背景：无检索能力时返回空上下文 + warning。
"""

from __future__ import annotations
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/test_generic_mining_context.py')

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__legacy_source_file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from knowledge_clear_tool.generic_knowledge_quality import (
    repair_self_contained_knowledge_rows,
    filter_business_quality_rows,
    is_generic_heading,
    has_dangling_reference,
    source_subject,
)
from knowledge_clear_tool.business_context_builder import build_business_context
from knowledge_clear_tool.chat_query_context import _is_meaningful_query, load_client_queries
from knowledge_clear_tool.web_business_context import build_web_business_context


# ---------------------------------------------------------------------------
# 通用质量后处理
# ---------------------------------------------------------------------------

def test_generic_heading_gets_subject_prefix():
    """栏目式泛标题 + from_file_name → 标题补上业务主体。"""
    rows = [{"title": "活动概述与目标", "content": "活动包含主题演讲与圆桌。",
             "from_file_name": "北美采购订单渠道对接会"}]
    repaired, report = repair_self_contained_knowledge_rows(rows)
    assert "北美采购订单渠道对接会" in repaired[0]["title"]
    assert report["repaired_count"] >= 1
    # 输出中不应再出现裸标题
    assert repaired[0]["title"] != "活动概述与目标"


def test_bare_column_titles_repaired():
    """适合对象/推广内容/服务内容 等裸标题都应补主体。"""
    for bare in ["适合对象", "推广内容", "服务内容"]:
        rows = [{"title": bare, "content": "包含具体步骤与条件，费用为1.2%。",
                 "from_file_name": "某某推广大使计划介绍"}]
        repaired, _ = repair_self_contained_knowledge_rows(rows)
        assert repaired[0]["title"] != bare, f"{bare} 未补主体"


def test_dangling_ordinal_marked_needs_review_and_rejected():
    """悬空“第一期…”无法补全 → needs_review，并被业务质量过滤拒绝。"""
    rows = [{"q": "第一期直播主要讨论什么", "a": "讨论了合规与增长相关议题。",
             "from_file_name": "某品牌系列直播预告"}]
    repaired, report = repair_self_contained_knowledge_rows(
        rows, title_field="q", content_field="a")
    assert repaired[0].get("needs_review") is True
    kept, rejected = filter_business_quality_rows(
        repaired, title_field="q", content_field="a")
    assert len(kept) == 0 and len(rejected) == 1
    assert rejected[0]["reject_reason"] == "needs_review_dangling_or_generic"


def test_boilerplate_rejected():
    """版权/关注公众号/阅读原文类内容必须进入 rejected。"""
    rows = [
        {"title": "版权声明", "content": "本文版权所有，转载请注明，欢迎关注公众号、点赞、阅读原文。",
         "from_file_name": "公众号文章"},
    ]
    kept, rejected = filter_business_quality_rows(rows)
    assert len(rejected) == 1 and rejected[0]["reject_reason"] == "boilerplate"


def test_thin_answer_rejected():
    """单薄、无具体值的答案被拒绝。"""
    rows = [{"title": "某平台收款服务介绍", "content": "很好用。", "from_file_name": "文章"}]
    kept, rejected = filter_business_quality_rows(rows)
    assert len(rejected) == 1 and rejected[0]["reject_reason"] == "thin_no_concrete_value"


def test_concrete_answer_kept():
    """含具体步骤/数值的自包含知识应保留。"""
    rows = [{"title": "某平台绑定收款账户的步骤是什么",
             "content": "Step 1 登录卖家中心；Step 2 进入财务-收款账户；费率1.2%。",
             "from_file_name": "平台收款指南"}]
    kept, rejected = filter_business_quality_rows(rows)
    assert len(kept) == 1 and len(rejected) == 0


def test_image_only_answer_rejected():
    """多模态没 OCR 出文字时，QA 生成会拿图片链接当答案，检索命中等于没答案。

    这类行以前能过：`_is_too_thin` 把裸 URL 当成「有具体值」直接放行。
    """
    rows = [{"title": "商家自运营(POP)模式和全托管模式的对比是什么？",
             "content": "https://file.marsmind.cc/kgmultimodal/knowledge/multimodal/"
                        "default/20260807/2add5df2acfc4d4192c7958cccb771d2.png",
             "from_file_name": "TikTok Shop 入驻攻略"}]
    kept, rejected = filter_business_quality_rows(rows)
    assert len(rejected) == 1 and rejected[0]["reject_reason"] == "image_only_no_text"


def test_image_only_markdown_form_rejected():
    rows = [{"title": "费用结构是怎样的？",
             "content": "![](https://cdn.example.com/a/b.png)\n\n![](https://cdn.example.com/a/c.jpg)",
             "from_file_name": "攻略"}]
    kept, rejected = filter_business_quality_rows(rows)
    assert len(rejected) == 1 and rejected[0]["reject_reason"] == "image_only_no_text"


def test_official_link_answer_still_kept():
    """指向官网/入驻通道的普通链接是有价值的答案，不能跟着图片链接一起被杀。"""
    rows = [{"title": "TikTok Shop 美区 ACCU 的官方入驻通道是什么？",
             "content": "https://seller-us-accounts.tiktok.com/account/accu/register"
                        "?channel=us_mkt_livestream（建议用海外IP登陆）",
             "from_file_name": "TikTok Shop 入驻攻略"}]
    kept, rejected = filter_business_quality_rows(rows)
    assert len(kept) == 1 and len(rejected) == 0


def test_image_plus_text_answer_kept():
    """图文混排、图旁边有实质说明的，仍然是有效知识。"""
    rows = [{"title": "美国主体商家入驻需要哪些材料？",
             "content": "需要美国公司注册文件、中国最终受益人证件、美国本地手机号。\n"
                        "![](https://cdn.example.com/a/b.png)",
             "from_file_name": "攻略"}]
    kept, rejected = filter_business_quality_rows(rows)
    assert len(kept) == 1 and len(rejected) == 0


def test_helpers():
    assert source_subject("北美采购订单渠道对接会：链接头部商超资源") == "北美采购订单渠道对接会"
    assert is_generic_heading("适合对象", subject="某计划", markers=[]) is True
    assert is_generic_heading("某计划的适合对象", subject="某计划", markers=[]) is False
    assert has_dangling_reference("本次活动如何报名") is True
    assert has_dangling_reference("第一期直播主题") is True


# ---------------------------------------------------------------------------
# 业务上下文构建 —— 兼容性
# ---------------------------------------------------------------------------

def test_context_disabled_no_enrichment(tmp_path):
    """enable_context_enrichment=false → 返回 enabled=False，不查 chat、不联网。"""
    ctx = build_business_context(
        client="payoneer",
        knowledge_objective=None,
        business_context_text=None,
        enable_context_enrichment=False,
        enable_chat_query_context=True,   # 即便为 true，总开关关闭也不应触发
        enable_web_context=True,
        cache_dir=str(tmp_path / "cache"),
    )
    assert ctx["enabled"] is False
    assert ctx["context_text"] == ""
    assert ctx["sources"]["chat_history"] is False
    assert ctx["sources"]["web_search"] is False


def test_context_frontend_only_no_chat_no_web(tmp_path):
    """只传 business_context_text，且 chat/web 关闭 → 生成上下文文件，不查库不联网。"""
    ctx = build_business_context(
        client="payoneer",
        knowledge_objective="平台收款、提现",
        business_context_text="客户是跨境支付平台，目标用户是跨境卖家。",
        enable_context_enrichment=True,
        enable_chat_query_context=False,
        enable_web_context=False,
        cache_dir=str(tmp_path / "cache"),
        now_ts=1000.0,
    )
    assert ctx["enabled"] is True
    assert "跨境支付平台" in ctx["context_text"]
    assert ctx["sources"]["frontend_context"] is True
    assert ctx["sources"]["chat_history"] is False
    assert ctx["sources"]["web_search"] is False
    assert os.path.exists(ctx["cache_path"])


def test_context_cache_hit(tmp_path):
    """相同入参第二次调用命中缓存。"""
    kwargs = dict(
        client="payoneer", knowledge_objective="x", business_context_text="bg",
        enable_context_enrichment=True, enable_chat_query_context=False,
        enable_web_context=False, cache_dir=str(tmp_path / "cache"), now_ts=1000.0,
    )
    first = build_business_context(**kwargs)
    assert first["cache_hit"] is False
    second = build_business_context(**kwargs)
    assert second["cache_hit"] is True


def test_context_query_exclude_terms_filter_and_cache_key(tmp_path, monkeypatch):
    from knowledge_clear_tool import chat_query_context

    monkeypatch.setattr(
        chat_query_context,
        "load_client_queries",
        lambda **kwargs: ["巴西站怎么参加活动", "阿根廷税务怎么配置", "如何开通Full"],
    )
    captured = []

    def summarize(queries, **kwargs):
        captured.append(list(queries))
        return [{"intent": query, "sample_queries": [query]} for query in queries]

    monkeypatch.setattr(chat_query_context, "summarize_query_intents", summarize)
    base = dict(
        client="mercado_local",
        knowledge_objective="阿根廷卖家知识",
        business_context_text="Mercado Libre Argentina",
        enable_context_enrichment=True,
        enable_chat_query_context=True,
        enable_web_context=False,
        cache_dir=str(tmp_path / "cache"),
        now_ts=1000.0,
    )

    filtered = build_business_context(
        **base, task_info={"chat_query_exclude_terms": ["巴西", "墨西哥"]}
    )
    unfiltered = build_business_context(**base, task_info={})

    assert captured[0] == ["阿根廷税务怎么配置", "如何开通Full"]
    assert filtered["cache_path"] != unfiltered["cache_path"]


# ---------------------------------------------------------------------------
# chat query 清洗 + 降级
# ---------------------------------------------------------------------------

def test_is_meaningful_query():
    assert _is_meaningful_query("Payoneer 提现费率是多少？") is True
    assert _is_meaningful_query("你好") is False
    assert _is_meaningful_query("https://x.com/a.png") is False
    assert _is_meaningful_query("😀😀") is False
    assert _is_meaningful_query("好的") is False


def test_load_client_queries_degrades_without_config(tmp_path):
    """指向不存在的 mysql 配置 → 降级返回空列表，不抛异常。"""
    result = load_client_queries(
        client="payoneer", mysql_config_path=str(tmp_path / "nope.json"))
    assert result == []


# ---------------------------------------------------------------------------
# web 业务背景 —— 默认无检索能力时降级
# ---------------------------------------------------------------------------

def test_web_context_no_search_callable(tmp_path):
    res = build_web_business_context(
        client="payoneer", knowledge_objective="收款",
        cache_dir=str(tmp_path / "web"), now_ts=1000.0)
    assert res["context_text"] == ""
    assert res["sources"]["web_search"] is False
    assert res["warning"]


def test_web_context_with_injected_search(tmp_path):
    res = build_web_business_context(
        client="payoneer", knowledge_objective="收款",
        cache_dir=str(tmp_path / "web"),
        search_callable=lambda q: "跨境支付平台，服务跨境卖家。",
        now_ts=1000.0)
    assert "跨境支付平台" in res["context_text"]
    assert res["sources"]["web_search"] is True


# --------------------------------------------------------------------------- 单薄判定

def test_concise_enumeration_answer_kept():
    """精炼的枚举式答案不能因为「短」被拒——老规则正是在这里误杀。"""
    rows = [{"title": "TikTok Shop首站可选地区有哪些？",
             "content": "目前首站可选（可一键全开）：菲律宾、马来西亚、泰国、越南、新加坡。",
             "from_file_name": "入驻攻略"}]
    kept, rejected = filter_business_quality_rows(rows)
    assert len(kept) == 1 and not rejected


def test_concise_qualification_answer_kept():
    rows = [{"title": "入驻资质要求是什么？",
             "content": "入驻要求提供有限公司资质/个人独资企业资质营业执照/个体工商户执照。",
             "from_file_name": "入驻攻略"}]
    kept, rejected = filter_business_quality_rows(rows)
    assert len(kept) == 1 and not rejected


def test_concise_operation_answer_kept():
    rows = [{"title": "如何发布商品？",
             "content": "在卖家后台，点击“商品”菜单，然后选择“去发布”即可添加并发布全球商品。",
             "from_file_name": "入驻攻略"}]
    kept, rejected = filter_business_quality_rows(rows)
    assert len(kept) == 1 and not rejected


def test_pointer_answer_rejected():
    """只把人指向别处、自身没有信息的答案要拒——哪怕它不算短。"""
    rows = [{"title": "平台佣金和交易手续费如何收取？",
             "content": "具体佣金规则和交易手续费因站点而异，请参考原文表格中的详细信息。",
             "from_file_name": "入驻攻略"}]
    kept, rejected = filter_business_quality_rows(rows)
    assert len(rejected) == 1 and rejected[0]["reject_reason"] == "thin_no_concrete_value"


def test_empty_praise_answer_still_rejected():
    rows = [{"title": "某平台收款服务介绍", "content": "很好用。", "from_file_name": "文章"}]
    kept, rejected = filter_business_quality_rows(rows)
    assert len(rejected) == 1 and rejected[0]["reject_reason"] == "thin_no_concrete_value"
