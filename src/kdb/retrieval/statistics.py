from datetime import datetime
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Union

def get_unique_values(self, index_name: str, field_name: str, size: int = 10000, include_doc_count: bool = False, extra_query: Optional[Dict[str, Any]] = None) -> Union[List[str], List[Dict[str, Any]]]:
    """
    获取指定字段的唯一值集合
    """
    return self.engine.get_unique_values(index_name, field_name, size, include_doc_count, extra_query)


def get_from_type_count(self, index_name: Optional[str], from_type: str = "chat_auto",
                        start: Optional[datetime] = None, end: Optional[datetime] = None) -> int:
    """统计high来源知识，保留原Java筛选口径，不加检索默认条件。"""
    if not index_name:
        return 0
    filters = [{"term": {"quality_level": "high"}}, {"term": {"from_type": from_type}}]
    if start is not None and end is not None:
        filters.append({"range": {"insert_time": {
            "gte": start.isoformat(sep=" ", timespec="seconds"),
            "lte": end.isoformat(sep=" ", timespec="seconds"),
        }}})
    return self.engine.count_by_query(index_name, {"bool": {"filter": filters}}, require_complete=True)
