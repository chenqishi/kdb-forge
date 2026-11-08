from datetime import datetime
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
import json
import logging
import os
logger = logging.getLogger('kdb.retrieval.application.search_index_data_interface')

def _bigrams(text: str) -> set:
    s = (text or "").strip().lower()
    return set(s[i:i + 2] for i in range(len(s) - 1)) or ({s} if s else set())


def dice_similarity(cls, a: str, b: str) -> float:
    """Dice 系数（按字符二元组）。两串完全相同为 1.0。"""
    A, B = cls._bigrams(a), cls._bigrams(b)
    if not A or not B:
        return 1.0 if (a or "") == (b or "") else 0.0
    return 2 * len(A & B) / (len(A) + len(B))


def _escape_wildcard(text: str) -> str:
    """转义 wildcard 语法字符，避免文件名里的 * ? 被当成通配。"""
    return (text or "").replace("\\", "\\\\").replace("*", "\\*").replace("?", "\\?")


def _scope_filters(self) -> List[Dict[str, Any]]:
    """所有查询共用的基础过滤：未删除 + 非对话来源。"""
    return [
        {"term": {"del_flag": 0}},
        {"terms": {"from_type_norm": list(self.FROM_TYPE_SCOPE)}},
    ]


def _build_file_query(self, file_names: List[str],
                      data_types: Optional[List[str]] = None,
                      audit_results: Optional[List[int]] = None) -> Dict[str, Any]:
    """构造「这些文件名 + 可选类型/审核状态」的 ES query。文件名一律精确匹配。

    文件名同时匹配 from_file_name 与 supersedes_file_name（OR）：
    文档重跑后新知识换了文件名，传旧名时要能连新知识一起删掉，否则旧的删了新的还在，
    等于没更新干净。两个字段任一命中即算该文件的知识。
    """
    must: List[Dict[str, Any]] = self._scope_filters()
    names = list(file_names)
    must.append({"bool": {"should": [
        {"terms": {self.FILE_NAME_KEYWORD: names}},
        {"terms": {self.SUPERSEDES_FIELD_KEYWORD: names}},
    ], "minimum_should_match": 1}})
    if data_types:
        must.append({"terms": {"data_type": list(data_types)}})
    if audit_results:
        must.append({"terms": {"audit_result": list(audit_results)}})
    return {"bool": {"must": must}}


def list_file_names(self, index_name: str, keyword: str = None,
                    size: int = 200, from_type_norm: Optional[str] = None) -> List[Dict[str, Any]]:
    """列出未删除知识的文件名及统计；来源为空时不限制来源。

    只读列表独立于删除范围；删除相关方法仍使用 _scope_filters 白名单。
    """
    must = [{"term": {"del_flag": 0}}]
    source_type = (from_type_norm or "").strip()
    if source_type:
        must.append({"term": {"from_type_norm": source_type}})
    if keyword:
        frag = self._escape_wildcard(keyword)[:self.MAX_WILDCARD_FRAGMENT]
        must.append({"wildcard": {self.FILE_NAME_KEYWORD:
                                  {"value": "*%s*" % frag, "case_insensitive": True}}})
    buckets = self.engine.agg_terms(
        index_name, {"bool": {"must": must}}, self.FILE_NAME_KEYWORD, size=size,
        sub_aggs={"by_type": {"terms": {"field": "data_type", "size": 10}}},
    )
    return [{"value": b["key"], "doc_count": b["doc_count"],
             "type_count": (b.get("sub") or {}).get("by_type", {})}
            for b in buckets]


def resolve_file_name(self, index_name: str, name: str,
                      match_mode: str = "exact") -> Dict[str, Any]:
    """把用户输入的文件名解析成库里真实存在的文件名。

    match_mode 严格二选一，没有兜底：
      - exact：只做 keyword 精确匹配；查不到就是查不到，不会转模糊
      - fuzzy：只做模糊召回 + Dice 判定；达不到阈值就是没找到，不会退回精确

    返回 {matched, matched_name, doc_count, dice, reason}
    """
    name = (name or "").strip()
    if not name:
        return {"matched": False, "matched_name": None, "doc_count": 0,
                "dice": 0.0, "reason": "文件名为空"}

    # .keyword 的 ignore_above 会让超长文件名根本没被索引，term 查不到且不报错。
    # 必须显式拦下来，否则用户以为删了、其实一条没删。
    if len(name) > self.KEYWORD_IGNORE_ABOVE:
        return {"matched": False, "matched_name": None, "doc_count": 0, "dice": 0.0,
                "reason": "文件名超过 %d 字符，未被索引为 keyword，无法按文件名匹配"
                          % self.KEYWORD_IGNORE_ABOVE}

    if match_mode == "exact":
        cnt = self.engine.count_by_query(
            index_name, self._build_file_query([name]))
        if cnt > 0:
            return {"matched": True, "matched_name": name, "doc_count": cnt,
                    "dice": 1.0, "reason": None}
        return {"matched": False, "matched_name": None, "doc_count": 0, "dice": 0.0,
                "reason": "精确匹配无结果"}

    if match_mode != "fuzzy":
        return {"matched": False, "matched_name": None, "doc_count": 0, "dice": 0.0,
                "reason": "match_mode 只能是 exact 或 fuzzy"}

    # fuzzy：下面几路都只负责「把候选捞全」，最终判定一律交给 Dice。
    #
    # 为什么不能只用 wildcard + match：
    #   - wildcard `*name*` 要求输入是真实名字的子串。用户多打一个字符
    #     （Text.docxx vs Text.docx）就不再是子串，捞不到。
    #   - 文件名字段的分词把 "text.docx" 切成**一个** token，
    #     所以 match 查 "text.docxx" 同样对不上。
    # 结果是"输错一个字"这种最典型的场景反而召不回。故再加两路：
    #   - fuzzy 查询：对 token 做编辑距离，救「多打/打错几个字符」
    #   - 前缀片段 wildcard：用输入的前一段做 `*frag*`，救「尾巴写错/写多」
    esc = self._escape_wildcard(name)
    frag = esc[:self.MAX_WILDCARD_FRAGMENT]
    # 取前 60% 作为前缀片段（至少 4 字符），让尾部写错时仍能命中
    prefix_len = max(4, min(len(esc) * 3 // 5, self.MAX_WILDCARD_FRAGMENT))
    prefix = esc[:prefix_len]
    shoulds = [
        {"wildcard": {self.FILE_NAME_KEYWORD:
                      {"value": "*%s*" % frag, "case_insensitive": True}}},
        {"match": {self.FILE_NAME_FIELD: {"query": name}}},
        {"match": {self.FILE_NAME_FIELD: {"query": name, "fuzziness": "AUTO"}}},
    ]
    if prefix and prefix != frag:
        shoulds.append({"wildcard": {self.FILE_NAME_KEYWORD:
                                     {"value": "*%s*" % prefix, "case_insensitive": True}}})
    query = {"bool": {
        "must": self._scope_filters(),
        "should": shoulds,
        "minimum_should_match": 1,
    }}
    buckets = self.engine.agg_terms(index_name, query, self.FILE_NAME_KEYWORD, size=80)
    best = None
    for b in buckets:
        score = self.dice_similarity(name, b["key"])
        if best is None or score > best[0]:
            best = (score, b["key"], b["doc_count"])
    if best and best[0] >= self.DICE_THRESHOLD:
        return {"matched": True, "matched_name": best[1], "doc_count": best[2],
                "dice": round(best[0], 4), "reason": None}
    return {"matched": False, "matched_name": None, "doc_count": 0,
            "dice": round(best[0], 4) if best else 0.0,
            "reason": "模糊匹配最高相似度 %.4f 未达阈值 %s"
                      % (best[0] if best else 0.0, self.DICE_THRESHOLD)}


def preview_delete_by_file(self, index_name: str, file_names: List[str],
                           match_mode: str = "exact",
                           data_types: Optional[List[str]] = None,
                           audit_results: Optional[List[int]] = None,
                           sample_size: int = 10) -> Dict[str, Any]:
    """预览按文件名删除会命中什么。只读，不改任何数据。"""
    by_file, warnings, resolved = [], [], []
    for raw in file_names:
        r = self.resolve_file_name(index_name, raw, match_mode)
        entry = {"input_name": raw, "matched": r["matched"],
                 "matched_name": r["matched_name"], "dice": r["dice"],
                 "count": r["doc_count"], "type_count": {}, "audit_count": {}}
        if not r["matched"]:
            entry["reason"] = r["reason"]
            warnings.append("「%s」未匹配到：%s" % (raw, r["reason"]))
        else:
            if match_mode == "fuzzy" and r["matched_name"] != raw:
                warnings.append("「%s」模糊匹配到「%s」(相似度 %.4f，%d 条)，请确认"
                                % (raw, r["matched_name"], r["dice"], r["doc_count"]))
            q = self._build_file_query([r["matched_name"]], data_types, audit_results)
            entry["count"] = self.engine.count_by_query(index_name, q)
            for b in self.engine.agg_terms(index_name, q, "data_type", size=10):
                entry["type_count"][b["key"]] = b["doc_count"]
            for b in self.engine.agg_terms(index_name, q, "audit_result", size=10):
                entry["audit_count"][str(b["key"])] = b["doc_count"]
            resolved.append(r["matched_name"])
        by_file.append(entry)

    total, type_count, samples = 0, {}, []
    if resolved:
        q = self._build_file_query(resolved, data_types, audit_results)
        total = self.engine.count_by_query(index_name, q)
        for b in self.engine.agg_terms(index_name, q, "data_type", size=10):
            type_count[b["key"]] = b["doc_count"]
        if sample_size:
            samples = self.engine.sample_by_query(
                index_name, q, size=sample_size,
                includes=["title", "content", "data_type", "audit_result",
                          "ext_info.from_file_name", "from_type_norm"])
            for s in samples:
                s["content"] = (s.get("content") or "")[:120]

    return {"total_count": total, "by_file": by_file, "type_count": type_count,
            "samples": samples, "warnings": warnings,
            "resolved_names": resolved}


def delete_by_file(self, index_name: str, file_names: List[str],
                   match_mode: str = "exact",
                   data_types: Optional[List[str]] = None,
                   audit_results: Optional[List[int]] = None,
                   snapshot_dir: str = "data/deleted_snapshots") -> Dict[str, Any]:
    """按文件名软删除（del_flag=1）。删前写快照，可回滚。

    入参与 preview_delete_by_file 完全一致，区别只是这个真删、那个不删。
    是否要让用户先看预览再确认，由前端流程决定，服务端不强制。
    """
    preview = self.preview_delete_by_file(
        index_name, file_names, match_mode, data_types, audit_results, sample_size=0)
    resolved = preview["resolved_names"]
    if not resolved:
        return {"success": False, "deleted_count": 0, "snapshot_path": None,
                "message": "没有匹配到任何文件名，未执行删除；" + "；".join(preview["warnings"])}

    query = self._build_file_query(resolved, data_types, audit_results)
    snapshot_path = self._dump_snapshot(index_name, query, snapshot_dir)
    result = self.engine.update_by_query(index_name, query, {"del_flag": 1})
    msg = "已软删除 %d 条" % result["updated"]
    if result.get("version_conflicts"):
        msg += "（版本冲突 %d 条已跳过）" % result["version_conflicts"]
    return {"success": True, "deleted_count": result["updated"],
            "snapshot_path": snapshot_path, "message": msg}


def _dump_snapshot(self, index_name: str, query: Dict[str, Any],
                   snapshot_dir: str) -> Optional[str]:
    """删除前把命中文档落盘（不含向量），供回滚。分批取，避免大结果集被分片取消。"""
    try:
        os.makedirs(snapshot_dir, exist_ok=True)
        path = os.path.join(
            snapshot_dir,
            "%s_%s.jsonl" % (index_name, datetime.now().strftime("%Y%m%d_%H%M%S")))
        total = self.engine.count_by_query(index_name, query)
        written, page_size = 0, 500
        with open(path, "w", encoding="utf-8") as fh:
            while written < total:
                body = {"query": query, "from": written, "size": page_size,
                        "_source": {"excludes": ["*embedding*", "indexes.embedding"]},
                        "sort": ["_doc"]}
                resp = self.engine._search_with_shard_check(index_name, body)
                hits = resp.get("hits", {}).get("hits", [])
                if not hits:
                    break
                for h in hits:
                    fh.write(json.dumps(dict(h.get("_source") or {}, _id=h.get("_id")),
                                        ensure_ascii=False) + "\n")
                written += len(hits)
        logger.info("删除快照已写入 %s，共 %d 条", path, written)
        return path
    except Exception as e:
        logger.error("写删除快照失败: %s", str(e))
        raise
